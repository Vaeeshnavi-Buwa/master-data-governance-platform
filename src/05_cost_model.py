"""
Cost of poor master data in rupees.

Open defects are joined to stock, consumption, spend, cross-border flows and launch
dates. Unit costs from config/cost_assumptions.yaml are sampled from triangular
distributions (Monte Carlo) to give P10/P50/P90, plus a tornado of the most
sensitive assumptions. Recurring annual cost and one-time exposure are reported separately.

Outputs: data/reports/cost_summary.json, cost_by_driver.csv, cost_by_rule.csv,
         cost_by_org_unit.csv, cost_tornado.csv, cost_distribution.csv
"""
import json

import duckdb
import numpy as np
import pandas as pd
import yaml

from config import DB_PATH, REPORTS, ROOT, SNAPSHOT_DATE

N = 20_000
rng = np.random.default_rng(7)
A = yaml.safe_load(open(ROOT / "config" / "cost_assumptions.yaml"))
con = duckdb.connect(str(DB_PATH), read_only=True)
q = lambda s: con.sql(s).df()

# ---------------------------------------------------------------------------
# 1. Facts: what each defect touches
# ---------------------------------------------------------------------------
exc = q("select rule_id, record_key, org_unit from marts.fct_dq_exceptions")
exc["matnr_or_lifnr"] = exc["record_key"].str.split("|").str[0]
exc["werks"] = exc["record_key"].str.split("|").str[1]
use = q("select matnr, werks, consumption_value_inr from staging.stg_usage_12m")
mbew = q("select matnr, werks, stock_qty, stock_value_inr, unit_price from staging.stg_mbew")
mara = q("select matnr, mtart, matkl, created_on from staging.stg_mara")
spend = q("select lifnr, bukrs, spend_inr from staging.stg_vendor_spend_12m")
orgs = q("select org_unit, cross_border from reference.org_units")
xb = set(orgs.loc[orgs.cross_border, "org_unit"])
active = use[use.consumption_value_inr > 0][["matnr", "werks"]]


def rows(rule):          # failing records of a rule
    return exc[exc.rule_id == rule]


def mat_plant_items(rules, only_active=True, only_xb=False):
    """(rule, matnr, werks, org_unit) for material- or plant-level rules."""
    out = []
    for r in rules:
        e = rows(r)
        if e.empty:
            continue
        if e["werks"].notna().any():          # plant-level key
            it = e.rename(columns={"matnr_or_lifnr": "matnr"})[["matnr", "werks", "org_unit"]]
        else:                                  # material-level -> all its plant rows
            it = e.rename(columns={"matnr_or_lifnr": "matnr"})[["matnr", "org_unit"]].merge(
                mbew[["matnr", "werks"]], on="matnr")
        if only_active:
            it = it.merge(active, on=["matnr", "werks"])
        if only_xb:
            it = it[it.werks.isin(xb)]
        out.append(it.assign(rule_id=r))
    return pd.concat(out) if out else pd.DataFrame(columns=["matnr", "werks", "org_unit", "rule_id"])


def dedupe_weights(items):
    """An item with 3 defects has 1 bad order, not 3: count distinct items, split credit across rules."""
    items = items.copy()
    items["w"] = 1 / items.groupby(["matnr", "werks"])["rule_id"].transform("count")
    return items


facts = {}
# duplicate materials
dm = rows("M10").rename(columns={"matnr_or_lifnr": "matnr"})
dm_stock = dm.merge(mbew, on="matnr")
dm_use = dm.merge(use, on="matnr")
facts["dup_mat_stock"] = dm_stock.stock_value_inr.sum()
facts["dup_mat_consumption"] = dm_use.consumption_value_inr.sum()
# duplicate vendors: spend on the duplicate record, and all spend in affected clusters
er_v = q("select lifnr, cluster_id, cluster_size from staging.stg_er_vendor")
dv = rows("V07").rename(columns={"matnr_or_lifnr": "lifnr"})
facts["dup_ven_record_spend"] = dv.merge(spend, on="lifnr").spend_inr.sum()
clusters = er_v[er_v.cluster_id.isin(er_v.merge(dv, on="lifnr").cluster_id)]
facts["dup_ven_cluster_spend"] = clusters.merge(spend, on="lifnr").spend_inr.sum()
# wrong orders
# only defects that directly break ordering: in-house flag (no PR), lead time, no controller,
# wrong base UoM (x1000 order errors), blocked-status items still orderable
wo = dedupe_weights(mat_plant_items(["P01", "P03", "P04", "P08", "M04"]))
facts["wrong_order_items"] = wo.w.sum()
so = mat_plant_items(["P02"])
facts["stockout_items"] = len(so)
ch = mat_plant_items(["P05"], only_xb=True)
facts["hs_missing_items"] = len(ch)
cw = dedupe_weights(mat_plant_items(["M02", "M03"], only_xb=True))
facts["weight_error_items"] = cw.w.sum()
# GST
gv = pd.concat([rows("V01"), rows("V02")]).rename(columns={"matnr_or_lifnr": "lifnr"})
gsp = gv.merge(spend[spend.bukrs == "1000"], on="lifnr")
facts["gst_spend_at_risk"] = gsp.spend_inr.sum()
# launches
fe = pd.concat([rows("M07"), rows("M08")]).rename(columns={"matnr_or_lifnr": "matnr"}).merge(mara, on="matnr")
recent = fe[pd.to_datetime(fe.created_on) >= pd.Timestamp(SNAPSHOT_DATE) - pd.Timedelta(days=A["launch_delays"]["new_sku_window_days"])]
facts["new_skus_blocked"] = recent.matnr.nunique()
facts["bad_ean_skus"] = rows("M08").shape[0]

# one-time exposures
m09 = rows("M09").rename(columns={"matnr_or_lifnr": "matnr"}).merge(mbew, on="matnr")
exposure = {"stranded_stock_deleted_materials": m09.stock_value_inr.sum()}
med = mbew.merge(mara, on="matnr")
med = med[med.unit_price > 0].groupby(["matkl", "werks"]).unit_price.median().rename("grp_median").reset_index()
p6 = rows("P06").rename(columns={"matnr_or_lifnr": "matnr"}).merge(mbew, on=["matnr", "werks"]).merge(mara, on="matnr").merge(med, on=["matkl", "werks"], how="left")
p7 = rows("P07").rename(columns={"matnr_or_lifnr": "matnr"}).merge(mbew, on=["matnr", "werks"]).merge(mara, on="matnr").merge(med, on=["matkl", "werks"], how="left")
exposure["inventory_understated_zero_price"] = (p6.stock_qty * p6.grp_median).sum()
exposure["inventory_misvalued_price_outliers"] = (p7.stock_qty * (p7.unit_price - p7.grp_median)).abs().sum()
v5 = rows("V05").rename(columns={"matnr_or_lifnr": "lifnr"}).merge(spend, on="lifnr")
exposure["spend_to_vendors_sharing_bank_accounts"] = v5.spend_inr.sum()
v8 = rows("V08").rename(columns={"matnr_or_lifnr": "lifnr"}).merge(spend, on="lifnr")
exposure["spend_to_posting_blocked_vendors"] = v8.spend_inr.sum()


# ---------------------------------------------------------------------------
# 2. Cost equations (vectorised over Monte Carlo draws)
# ---------------------------------------------------------------------------
def tri(d, n=N):
    return rng.triangular(d["low"], d["base"], d["high"], n) if isinstance(d, dict) else np.full(n, d)


def base(d):
    return d["base"] if isinstance(d, dict) else d


def drivers(P):
    """P: dict of parameter -> array (or scalar). Returns driver -> cost."""
    f = facts
    out = {}
    out["Duplicate materials: carrying + obsolescence"] = f["dup_mat_stock"] * (
        P["dm.carry"] * P["dm.excess"] + P["dm.obs"])
    out["Duplicate materials: lost price leverage"] = f["dup_mat_consumption"] * P["dm.lev"]
    out["Duplicate vendors: duplicate payments"] = f["dup_ven_cluster_spend"] * P["dv.pay"]
    out["Duplicate vendors: lost volume discounts"] = f["dup_ven_record_spend"] * P["dv.disc"]
    out["Wrong orders (MRP / purchasing data)"] = f["wrong_order_items"] * P["wo.n"] * P["wo.cost"]
    out["Stock-outs (reorder point = 0)"] = f["stockout_items"] * P["so.p"] * P["so.line"] * P["so.h"] * P["so.c"]
    hold = P["ch.days"] * P["ch.dem"] + P["ch.brk"]
    out["Customs holds (HS code / origin / weights)"] = (
        f["hs_missing_items"] * P["ch.xb"] * P["ch.ship"] * P["ch.p"] * hold
        + f["weight_error_items"] * P["ch.xb"] * P["ch.ship"] * P["ch.p"] * P["ch.wf"] * hold)
    itc = f["gst_spend_at_risk"] * P["gst.rate"]
    out["GST input-tax-credit leakage"] = itc * P["gst.lost"] + itc * (1 - P["gst.lost"]) * P["gst.coc"] * P["gst.m"] / 12
    out["Launch delays & retailer chargebacks"] = (
        f["new_skus_blocked"] * P["ld.days"] * P["ld.rev"] / 365 * P["ld.cm"] + f["bad_ean_skus"] * P["ld.cb"])
    return out


PMAP = {
    "dm.carry": A["duplicate_materials"]["carrying_cost_rate"], "dm.excess": A["duplicate_materials"]["excess_share_of_dup_stock"],
    "dm.obs": A["duplicate_materials"]["annual_obsolescence_rate"], "dm.lev": A["duplicate_materials"]["price_leverage_lost"],
    "dv.pay": A["duplicate_vendors"]["duplicate_payment_rate"], "dv.disc": A["duplicate_vendors"]["volume_discount_lost"],
    "wo.n": A["wrong_orders"]["incidents_per_affected_item_yr"], "wo.cost": A["wrong_orders"]["cost_per_incident_inr"],
    "so.p": A["stockouts"]["stockout_probability_yr"], "so.line": A["stockouts"]["share_stockouts_stopping_line"], "so.h": A["stockouts"]["line_down_hours"],
    "so.c": A["stockouts"]["contribution_per_line_hour_inr"],
    "ch.xb": A["compliance_holds"]["share_items_crossing_border"], "ch.ship": A["compliance_holds"]["shipments_per_item_yr"], "ch.p": A["compliance_holds"]["hold_probability"],
    "ch.days": A["compliance_holds"]["hold_days"], "ch.dem": A["compliance_holds"]["demurrage_per_day_inr"],
    "ch.brk": A["compliance_holds"]["broker_rework_inr"], "ch.wf": A["compliance_holds"]["weight_error_hold_factor"],
    "gst.rate": A["gst_itc"]["gst_rate"], "gst.lost": A["gst_itc"]["itc_permanently_lost"],
    "gst.m": A["gst_itc"]["delay_months"], "gst.coc": A["gst_itc"]["cost_of_capital"],
    "ld.days": A["launch_delays"]["delay_days"], "ld.rev": A["launch_delays"]["new_sku_annual_revenue_inr"],
    "ld.cm": A["launch_delays"]["contribution_margin"], "ld.cb": A["launch_delays"]["retailer_chargeback_per_bad_ean_yr"],
}
LABELS = {"dm.carry": "Inventory carrying rate", "dm.excess": "Excess share of duplicate stock", "dm.obs": "Obsolescence rate",
          "dm.lev": "Price leverage lost on duplicate SKUs", "dv.pay": "Duplicate payment rate", "dv.disc": "Volume discount lost",
          "wo.n": "Wrong-order incidents / item / yr", "wo.cost": "Cost per wrong-order incident", "so.p": "Stock-out probability", "so.line": "Share of stock-outs stopping a line", "ch.xb": "Share of items crossing a border",
          "so.h": "Line-down hours per stock-out", "so.c": "Contribution per line hour", "ch.ship": "Shipments / item / yr",
          "ch.p": "Customs hold probability", "ch.days": "Hold days", "ch.dem": "Demurrage / day", "ch.brk": "Broker rework",
          "ch.wf": "Weight-error hold factor", "gst.rate": "GST rate", "gst.lost": "ITC permanently lost",
          "gst.m": "ITC delay months", "gst.coc": "Cost of capital", "ld.days": "Launch delay days",
          "ld.rev": "New-SKU annual revenue", "ld.cm": "Contribution margin", "ld.cb": "Chargeback per bad EAN"}

draws = {k: tri(v) for k, v in PMAP.items()}
sim = drivers(draws)
total = sum(sim.values())
base_P = {k: base(v) for k, v in PMAP.items()}
base_d = drivers(base_P)
base_total = sum(base_d.values())

# tornado: one parameter at a time, low vs high
torn = []
for k, v in PMAP.items():
    if not isinstance(v, dict):
        continue
    lo = sum(drivers({**base_P, k: v["low"]}).values())
    hi = sum(drivers({**base_P, k: v["high"]}).values())
    torn.append(dict(parameter=LABELS[k], low_total=lo, high_total=hi, swing=abs(hi - lo)))
torn = pd.DataFrame(torn).sort_values("swing", ascending=False)

# ---------------------------------------------------------------------------
# 3. Attribution to rules and org units (base case)
# ---------------------------------------------------------------------------
per_rule = {}
def add(rule, v):
    per_rule[rule] = per_rule.get(rule, 0) + v

add("M10", base_d["Duplicate materials: carrying + obsolescence"] + base_d["Duplicate materials: lost price leverage"])
add("V07", base_d["Duplicate vendors: duplicate payments"] + base_d["Duplicate vendors: lost volume discounts"])
for r, w in wo.groupby("rule_id").w.sum().items():
    add(r, base_d["Wrong orders (MRP / purchasing data)"] * w / wo.w.sum())
add("P02", base_d["Stock-outs (reorder point = 0)"])
hold = base_P["ch.days"] * base_P["ch.dem"] + base_P["ch.brk"]
hs_cost = facts["hs_missing_items"] * base_P["ch.xb"] * base_P["ch.ship"] * base_P["ch.p"] * hold
add("P05", hs_cost)
for r, w in cw.groupby("rule_id").w.sum().items():
    add(r, (base_d["Customs holds (HS code / origin / weights)"] - hs_cost) * w / max(cw.w.sum(), 1e-9))
gshare = gsp.groupby("rule_id").spend_inr.sum() / max(gsp.spend_inr.sum(), 1)
for r, s in gshare.items():
    add(r, base_d["GST input-tax-credit leakage"] * s)
ld_launch = facts["new_skus_blocked"] * base_P["ld.days"] * base_P["ld.rev"] / 365 * base_P["ld.cm"]
rshare = recent.groupby("rule_id").matnr.nunique()
for r, n in rshare.items():
    add(r, ld_launch * n / rshare.sum())
add("M08", facts["bad_ean_skus"] * base_P["ld.cb"])
cat = pd.read_csv(ROOT / "dbt_mdg" / "seeds" / "dq_rule_catalog.csv")
by_rule = (pd.Series(per_rule, name="annual_cost_inr").rename_axis("rule_id").reset_index()
           .merge(cat[["rule_id", "description", "owner_function", "severity"]], on="rule_id", how="right").fillna({"annual_cost_inr": 0}))
open_counts = exc.groupby("rule_id").size().rename("open_defects")
by_rule = by_rule.merge(open_counts, on="rule_id", how="left").fillna({"open_defects": 0})
by_rule["cost_per_defect_inr"] = (by_rule.annual_cost_inr / by_rule.open_defects.replace(0, np.nan)).round(0)
by_rule = by_rule.sort_values("annual_cost_inr", ascending=False)
by_rule["cum_share"] = by_rule.annual_cost_inr.cumsum() / by_rule.annual_cost_inr.sum()

# org units: allocate each rule's cost by that rule's defect count per org unit
alloc = exc.groupby(["rule_id", "org_unit"]).size().rename("n").reset_index()
alloc["share"] = alloc.n / alloc.groupby("rule_id").n.transform("sum")
alloc = alloc.merge(by_rule[["rule_id", "annual_cost_inr"]], on="rule_id")
by_org = (alloc.assign(cost=alloc.share * alloc.annual_cost_inr).groupby("org_unit").cost.sum()
          .rename("annual_cost_inr").sort_values(ascending=False).reset_index())

# ---------------------------------------------------------------------------
# 4. Programme economics
# ---------------------------------------------------------------------------
prog = A["program"]["annual_cost_inr"]
one_time = A["program"]["one_time_cost_inr"]
removed = tri(A["program"]["share_of_recurring_cost_removed_yr1"])
benefit = total * removed
roi = (benefit - prog - one_time) / (prog + one_time)            # year-1, all-in
payback = 12 * (one_time + prog) / benefit                        # months of benefit to recover yr-1 spend
p = lambda a, x: float(np.percentile(a, x))
summary = dict(
    snapshot_date=str(SNAPSHOT_DATE),
    annual_recurring_cost_inr=dict(p10=p(total, 10), p50=p(total, 50), p90=p(total, 90), base_case=base_total),
    one_time_exposure_inr={k: round(float(v), 2) for k, v in exposure.items()},
    program=dict(annual_cost_inr=prog, one_time_cost_inr=one_time, yr1_benefit_p10=p(benefit, 10),
                 yr1_benefit_p50=p(benefit, 50), yr1_benefit_p90=p(benefit, 90), yr1_roi_p50=p(roi, 50),
                 payback_months_p50=p(payback, 50), payback_months_p90=p(payback, 90),
                 prob_yr1_benefit_exceeds_total_cost=float((benefit > prog + one_time).mean())),
    top3_rules_share_of_cost=float(by_rule.head(3).annual_cost_inr.sum() / by_rule.annual_cost_inr.sum()),
    facts={k: float(v) for k, v in facts.items()},
)
REPORTS.mkdir(exist_ok=True, parents=True)
(REPORTS / "cost_summary.json").write_text(json.dumps(summary, indent=2))
pd.DataFrame({k: dict(base_case=base_d[k], p10=p(v, 10), p50=p(v, 50), p90=p(v, 90)) for k, v in sim.items()}).T \
    .rename_axis("driver").reset_index().sort_values("base_case", ascending=False).to_csv(REPORTS / "cost_by_driver.csv", index=False)
by_rule.to_csv(REPORTS / "cost_by_rule.csv", index=False)
by_org.to_csv(REPORTS / "cost_by_org_unit.csv", index=False)
torn.to_csv(REPORTS / "cost_tornado.csv", index=False)
pd.DataFrame({"total_inr": np.percentile(total, np.arange(0, 101))}).to_csv(REPORTS / "cost_distribution.csv", index_label="pct")

cr = lambda x: f"Rs {x / 1e7:,.2f} Cr"
print("Annual recurring cost of poor master data:")
print(f"  P10 {cr(p(total, 10))} | P50 {cr(p(total, 50))} | P90 {cr(p(total, 90))}   (base case {cr(base_total)})")
for k, v in sorted(base_d.items(), key=lambda kv: -kv[1]):
    print(f"   {k:48s} {cr(v)}")
print("One-time exposure:")
for k, v in exposure.items():
    print(f"   {k:48s} {cr(v)}")
print(f"Programme: run {cr(prog)}/yr + one-time {cr(one_time)}; yr-1 benefit P50 {cr(p(benefit, 50))} "
      f"(P10 {cr(p(benefit, 10))}); yr-1 ROI P50 {p(roi, 50):.1f}x; payback P50 {p(payback, 50):.1f} months "
      f"(P90 {p(payback, 90):.1f}); P(yr-1 benefit > all yr-1 cost) = {(benefit > prog + one_time).mean():.0%}")
print(f"Top 3 rules = {summary['top3_rules_share_of_cost']:.0%} of cost:", ", ".join(by_rule.head(3).rule_id))
print("Tornado (top 5):"); print(torn.head(5).to_string(index=False))
