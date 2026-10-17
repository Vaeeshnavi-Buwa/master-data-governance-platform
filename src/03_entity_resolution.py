"""
Duplicate detection with Splink (Fellegi-Sunter, EM-trained) and survivorship to golden records.

Fuzzy matching on a single field with a fixed cut-off flagged far too many false pairs
(20 vs 25 micron film looks almost identical as a string). Splink weighs each field
separately and returns a match probability, which is split into auto-merge,
steward review and reject bands.

Outputs (data/processed):
  er_material_clusters, er_vendor_clusters
  er_material_review_queue, er_vendor_review_queue
  golden_material, golden_vendor, xref_material, xref_vendor, merge_plan_material
  data/reports/er_metrics.json, er_threshold_curve.csv, splink charts
"""
from __future__ import annotations

import json
import re
import time
import warnings
from itertools import combinations

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process
from rapidfuzz.distance import DamerauLevenshtein
from splink import DuckDBAPI, Linker, SettingsCreator, block_on
import splink.comparison_library as cl
import splink.comparison_level_library as cll

from config import PROCESSED, RAW, REPORTS
from reference_data import num_signature, phone_digits, std_city, std_material_desc, std_vendor_name

warnings.filterwarnings("ignore")
PROCESSED.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)



# =============================================================================
# Evaluation helpers - pairwise precision / recall against ground truth
# =============================================================================
def pairs_from_clusters(df: pd.DataFrame, id_col: str, cl_col: str) -> set:
    out = set()
    for _, g in df.groupby(cl_col):
        ids = sorted(g[id_col])
        if len(ids) > 1:
            out.update(combinations(ids, 2))
    return out


def score(pred: set, truth: set) -> dict:
    tp = len(pred & truth)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(truth) if truth else 0.0
    return dict(pred_pairs=len(pred), true_pairs=len(truth), tp=tp, fp=len(pred) - tp, fn=len(truth) - tp,
                precision=round(p, 4), recall=round(r, 4), f1=round(2 * p * r / (p + r), 4) if p + r else 0.0)


def fuzzy_baseline(df, id_col, text_col, group_col, cutoff=90):
    """Baseline: token_sort_ratio >= 90 within a group."""
    pairs = set()
    for _, g in df.groupby(group_col):
        if len(g) < 2:
            continue
        ids = g[id_col].tolist(); txt = g[text_col].fillna("").tolist()
        m = process.cdist(txt, txt, scorer=fuzz.token_sort_ratio, score_cutoff=cutoff, workers=-1, dtype=np.uint8)
        ii, jj = np.nonzero(np.triu(m, 1))
        pairs.update((min(ids[a], ids[b]), max(ids[a], ids[b])) for a, b in zip(ii, jj))
    return pairs


def cluster_at(linker, pred, thr, id_col):
    c = linker.clustering.cluster_pairwise_predictions_at_threshold(pred, threshold_match_probability=thr).as_pandas_dataframe()
    return c.rename(columns={"unique_id": id_col})[[id_col, "cluster_id"]] if "unique_id" in c.columns else c[[id_col, "cluster_id"]]


# =============================================================================
# 1. MATERIALS
# =============================================================================
t0 = time.time()
print("== Materials ==")
mara = pd.read_parquet(RAW / "mara.parquet")
makt = pd.read_parquet(RAW / "makt.parquet")
marc = pd.read_parquet(RAW / "marc.parquet")
mbew = pd.read_parquet(RAW / "mbew.parquet")
desc_e = makt[makt.SPRAS == "E"].set_index("MATNR")["MAKTX"]
desc_any = makt.groupby("MATNR")["MAKTX"].first()

m = mara[["MATNR", "MTART", "MATKL", "MEINS", "BRGEW", "MFRPN", "MFRNR", "EAN11", "ERSDA"]].copy()
m["desc_raw"] = m["MATNR"].map(desc_e).fillna(m["MATNR"].map(desc_any))
m["desc_std"] = m["desc_raw"].map(std_material_desc)
m["desc_sorted"] = m["desc_std"].map(lambda s: " ".join(sorted(s.split())))
m["num_sig"] = m["desc_std"].map(num_signature).replace("", None)
m["first_tok"] = m["desc_std"].str.split().str[0]
# words and numbers are separate kinds of evidence: a typo in a word is noise,
# a different number (20 vs 25 micron) is a different material.
# Vocabulary-based spelling correction: words used by >= 15 materials form the
# controlled vocabulary; a rare long word within 2 edits of a vocabulary word is
# treated as a typo of it. Short tokens (IPA/NPA, LDPE/HDPE) are never "corrected"
# - there a one-letter difference is a different chemical.
_tok = pd.Series([t for s in m["desc_std"] for t in s.split() if not any(c.isdigit() for c in t)])
_freq = _tok.value_counts()
VOCAB = list(_freq[_freq >= 15].index)
_fix_cache = {}


def fix_token(t):
    if t in _fix_cache:
        return _fix_cache[t]
    out = t
    if len(t) >= 5 and _freq.get(t, 0) < 15:
        hit = process.extractOne(t, VOCAB, scorer=DamerauLevenshtein.distance, score_cutoff=2)
        if hit and abs(len(hit[0]) - len(t)) <= 2:
            out = hit[0]
    _fix_cache[t] = out
    return out


m["word_sig"] = m["desc_std"].map(
    lambda s: " ".join(sorted(fix_token(t) for t in s.split() if not any(c.isdigit() for c in t)))).replace("", None)
print(f"  vocabulary={len(VOCAB)} words, typo corrections applied={sum(k != v for k, v in _fix_cache.items())}")
m["mfr_key"] = (m["MFRNR"].fillna("") + "|" + m["MFRPN"]).where(m["MFRPN"].notna())
m["brgew"] = m["BRGEW"].astype(float)
m = m.rename(columns={"MATNR": "unique_id"})
feat_m = m[["unique_id", "MTART", "MATKL", "MEINS", "brgew", "mfr_key", "EAN11", "word_sig", "num_sig"]]

weight_cmp = cl.CustomComparison(
    output_column_name="brgew",
    comparison_levels=[
        cll.NullLevel("brgew"),
        cll.ExactMatchLevel("brgew"),
        cll.CustomLevel("abs(brgew_l - brgew_r) / greatest(brgew_l, brgew_r) <= 0.03", label_for_charts="within 3%"),
        cll.ElseLevel(),
    ])

settings_m = SettingsCreator(
    link_type="dedupe_only",
    comparisons=[
        # after vocabulary correction, words either agree or they don't: a one-letter
        # difference left over is IPA vs NPA or LDPE vs HDPE - a DIFFERENT product.
        cl.ExactMatch("word_sig"),
        cl.ExactMatch("num_sig"),
        cl.ExactMatch("MATKL"),
        # UoM and weight removed: near-constant within a material group, so they
        # double-count MATKL and break the independence assumption (more false positives).
        cl.ExactMatch("mfr_key"),
        cl.ExactMatch("EAN11"),
    ],
    blocking_rules_to_generate_predictions=[
        block_on("MTART", "num_sig"),
        block_on("mfr_key"),
        block_on("EAN11"),
    ],
    retain_intermediate_calculation_columns=False,
)
linker_m = Linker(feat_m, settings_m, DuckDBAPI())
linker_m.training.estimate_probability_two_random_records_match(
    [block_on("num_sig", "word_sig"), block_on("EAN11")], recall=0.7)
linker_m.training.estimate_u_using_random_sampling(max_pairs=5e6, seed=1)
linker_m.training.estimate_parameters_using_expectation_maximisation(block_on("MTART", "num_sig"))
linker_m.training.estimate_parameters_using_expectation_maximisation(block_on("EAN11"))
linker_m.training.estimate_parameters_using_expectation_maximisation(block_on("mfr_key"))
pred_m = linker_m.inference.predict(threshold_match_probability=0.3)
pairs_m = pred_m.as_pandas_dataframe()
print(f"  candidate pairs scored >=0.3: {len(pairs_m):,}  ({time.time()-t0:.0f}s)")

truth_m = pd.read_parquet(RAW / "_truth_material_entities.parquet")
true_pairs_m = pairs_from_clusters(truth_m, "MATNR", "entity_id")

curve = []
for thr in [0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 0.999]:
    c = cluster_at(linker_m, pred_m, thr, "unique_id")
    s = score(pairs_from_clusters(c, "unique_id", "cluster_id"), true_pairs_m)
    curve.append(dict(domain="material", threshold=thr, **s))
    print(f"  thr={thr:<6} P={s['precision']:.3f} R={s['recall']:.3f} F1={s['f1']:.3f}")
best_m = max(curve, key=lambda r: r["f1"])
clus_m = cluster_at(linker_m, pred_m, best_m["threshold"], "unique_id").rename(columns={"unique_id": "MATNR"})

base_m = fuzzy_baseline(m.rename(columns={"unique_id": "MATNR"}), "MATNR", "desc_raw", "MATKL", 90)
base_m_s = score(base_m, true_pairs_m)
print(f"  baseline fuzzy>=90 within MATKL: P={base_m_s['precision']:.3f} R={base_m_s['recall']:.3f} F1={base_m_s['f1']:.3f}")
try:
    linker_m.visualisations.match_weights_chart().save(str(REPORTS / "splink_material_match_weights.html"))
except Exception as e:  # charts are nice-to-have
    print("  (chart skipped)", e)

# =============================================================================
# 2. VENDORS
# =============================================================================
t0 = time.time()
print("== Vendors ==")
lfa1 = pd.read_parquet(RAW / "lfa1.parquet")
lfbk = pd.read_parquet(RAW / "lfbk.parquet")
v = lfa1.copy()
v["name_std"] = v["NAME1"].map(std_vendor_name)
v["name_key"] = v["name_std"].str[:5]
v["city_std"] = v["ORT01"].map(std_city)
v["postcode"] = v["PSTLZ"].replace("", None)
v["pan"] = v["STCD3"].where(v["STCD3"].str.len() >= 12).str[2:12]
v["phone"] = v["TELF1"].map(phone_digits)
v["email"] = v["SMTP_ADDR"].str.lower()
v = v.merge(lfbk[["LIFNR", "BANKN"]], on="LIFNR", how="left")
v = v.rename(columns={"LIFNR": "unique_id"})
feat_v = v[["unique_id", "LAND1", "name_std", "name_key", "city_std", "postcode", "pan", "phone", "email", "BANKN"]]

loc_cmp = cl.CustomComparison(
    output_column_name="location",
    comparison_levels=[
        cll.CustomLevel("(city_std_l IS NULL OR city_std_r IS NULL)", label_for_charts="null").configure(is_null_level=True),
        cll.CustomLevel("postcode_l = postcode_r AND city_std_l = city_std_r", label_for_charts="same postcode"),
        cll.CustomLevel("city_std_l = city_std_r", label_for_charts="same city"),
        cll.ElseLevel(),
    ])
settings_v = SettingsCreator(
    link_type="dedupe_only",
    comparisons=[
        cl.JaroWinklerAtThresholds("name_std", [0.97, 0.92, 0.85]),
        loc_cmp,   # postcode and city combined: postcode implies city, counting both double-counts evidence
        cl.ExactMatch("pan"),
        cl.ExactMatch("phone"),
        cl.ExactMatch("email"),
        cl.ExactMatch("BANKN"),
    ],
    blocking_rules_to_generate_predictions=[
        block_on("pan"),
        block_on("phone"),
        block_on("BANKN"),
        block_on("LAND1", "name_key"),
        block_on("postcode"),
    ],
    retain_intermediate_calculation_columns=False,
)
linker_v = Linker(feat_v, settings_v, DuckDBAPI())
linker_v.training.estimate_probability_two_random_records_match(
    [block_on("pan"), block_on("name_std", "city_std")], recall=0.7)
linker_v.training.estimate_u_using_random_sampling(max_pairs=5e6, seed=1)
linker_v.training.estimate_parameters_using_expectation_maximisation(block_on("LAND1", "name_key"))
linker_v.training.estimate_parameters_using_expectation_maximisation(block_on("pan"))
linker_v.training.estimate_parameters_using_expectation_maximisation(block_on("postcode"))
pred_v = linker_v.inference.predict(threshold_match_probability=0.3)
pairs_v = pred_v.as_pandas_dataframe()
print(f"  candidate pairs scored >=0.3: {len(pairs_v):,}  ({time.time()-t0:.0f}s)")

truth_v = pd.read_parquet(RAW / "_truth_vendor_entities.parquet")
true_pairs_v = pairs_from_clusters(truth_v, "LIFNR", "entity_id")
for thr in [0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 0.999]:
    c = cluster_at(linker_v, pred_v, thr, "unique_id")
    s = score(pairs_from_clusters(c, "unique_id", "cluster_id"), true_pairs_v)
    curve.append(dict(domain="vendor", threshold=thr, **s))
    print(f"  thr={thr:<6} P={s['precision']:.3f} R={s['recall']:.3f} F1={s['f1']:.3f}")
best_v = max([r for r in curve if r["domain"] == "vendor"], key=lambda r: r["f1"])
clus_v = cluster_at(linker_v, pred_v, best_v["threshold"], "unique_id").rename(columns={"unique_id": "LIFNR"})
base_v = fuzzy_baseline(v.rename(columns={"unique_id": "LIFNR"}), "LIFNR", "NAME1", "LAND1", 90)
base_v_s = score(base_v, true_pairs_v)
print(f"  baseline fuzzy>=90 within country: P={base_v_s['precision']:.3f} R={base_v_s['recall']:.3f} F1={base_v_s['f1']:.3f}")
try:
    linker_v.visualisations.match_weights_chart().save(str(REPORTS / "splink_vendor_match_weights.html"))
except Exception as e:
    print("  (chart skipped)", e)

# =============================================================================
# 3. Review queues (pairs between the merge and reject thresholds)
# =============================================================================
def bands_for(domain):
    """Auto-merge where the labelled evaluation shows >=99.5% precision;
    anything between 0.5 and that goes to a steward. In production the labels
    come from stewards reviewing a sample each quarter, not from a generator."""
    c = [r for r in curve if r["domain"] == domain]
    auto = min([r["threshold"] for r in c if r["precision"] >= 0.995] or [0.999])
    return max(auto, 0.95), 0.5   # policy floor: never auto-merge below 0.95 (merges move stock & money)


bands, queues = {}, {}
for name, p in (("material", pairs_m), ("vendor", pairs_v)):
    auto, rev = bands_for(name)
    q = p[(p.match_probability >= rev) & (p.match_probability < auto)].copy()
    q["decision_band"] = "STEWARD_REVIEW"
    queues[name] = q[["unique_id_l", "unique_id_r", "match_probability", "match_weight", "decision_band"]]
    bands[name] = dict(auto_merge_threshold=auto, review_threshold=rev,
                       auto_merge_pairs=int((p.match_probability >= auto).sum()),
                       steward_review_pairs=len(q), rejected_pairs=int((p.match_probability < rev).sum()))
rq_m, rq_v = queues["material"], queues["vendor"]

# =============================================================================
# 4. Survivorship -> golden records
# =============================================================================
print("== Survivorship ==")
EAN_OK = lambda e: isinstance(e, str) and len(e) == 13 and e.isdigit() and int(e[12]) == (10 - sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(e[:12])) % 10) % 10
NAMING_OK = lambda s: isinstance(s, str) and s == s.upper() and s == s.strip() and "  " not in s and not re.search(r"\b(TEST|DO NOT USE|DUMMY)\b", s)

plants = marc.groupby("MATNR")["WERKS"].apply(lambda s: sorted(s)).rename("plants")
stock = mbew.groupby("MATNR")["SALK3"].sum().rename("stock_value")
mm = (mara.merge(clus_m, on="MATNR").merge(plants, on="MATNR", how="left").merge(stock, on="MATNR", how="left")
      .assign(desc=lambda d: d["MATNR"].map(desc_e)))
mm["n_plants"] = mm["plants"].map(len)
mm["stock_value"] = mm["stock_value"].fillna(0)
# survivor rule: most plant extensions -> most stock -> oldest (keeps open orders/BOMs on the record with most history)
mm = mm.sort_values(["cluster_id", "n_plants", "stock_value", "ERSDA"], ascending=[True, False, False, True])
mm["is_survivor"] = ~mm.duplicated("cluster_id")


def mode(s):
    s = s.dropna()
    return s.mode().iloc[0] if len(s) else None


golden_m, merge_plan = [], []
multi = mm[mm.groupby("cluster_id")["MATNR"].transform("size") > 1]
for cid, g in multi.groupby("cluster_id"):
    s = g.iloc[0]
    # golden description: prefer text that is already canonical (convention-compliant AND unchanged by
    # standardisation, i.e. no abbreviations/typos), oldest record first; else the standardised survivor text
    cand = g.sort_values("ERSDA")["desc"]
    good_desc = [d for d in cand if NAMING_OK(d) and d == std_material_desc(d)] or [std_material_desc(s.desc)[:40]]
    wt_ok = g[(g.NTGEW <= g.BRGEW) & g.GEWEI.notna()]
    wsrc = wt_ok.iloc[0] if len(wt_ok) else s
    eans = [e for e in g["EAN11"] if EAN_OK(e)]
    golden_m.append(dict(
        golden_id=f"GM{cid}", survivor_matnr=s.MATNR, members=len(g), MTART=s.MTART,
        MATKL=mode(g.MATKL), MEINS=s.MEINS if s.MEINS else mode(g.MEINS),
        MAKTX=good_desc[0],
        BRGEW=wsrc.BRGEW, NTGEW=wsrc.NTGEW, GEWEI="KG",
        EAN11=eans[0] if eans else None, PRDHA=mode(g.PRDHA),
        plants_union=",".join(sorted(set(sum(g["plants"], [])))),
        total_stock_value=round(g.stock_value.sum(), 2)))
    for _, r in g.iloc[1:].iterrows():
        new_plants = [p for p in r.plants if p not in s.plants]
        merge_plan.append(dict(golden_id=f"GM{cid}", survivor_matnr=s.MATNR, retire_matnr=r.MATNR,
                               extend_survivor_to=",".join(new_plants), stock_to_transfer_inr=round(r.stock_value, 2),
                               actions="1) extend survivor to plants 2) transfer stock (MIGO 309) 3) repoint BOMs, "
                                       "info records, source lists 4) set X-plant status BL + deletion flag 5) BISMT/xref"))
golden_m = pd.DataFrame(golden_m)
merge_plan = pd.DataFrame(merge_plan)
xref_m = mm[["MATNR", "cluster_id", "is_survivor"]].copy()
surv = mm[mm.is_survivor].set_index("cluster_id")["MATNR"]
xref_m["golden_matnr"] = xref_m["cluster_id"].map(surv)

# vendors
spend = pd.read_parquet(RAW / "vendor_spend_12m.parquet").groupby("LIFNR")["SPEND_12M_INR"].sum()
lfb1 = pd.read_parquet(RAW / "lfb1.parquet")
vv = lfa1.merge(clus_v, on="LIFNR").merge(lfbk[["LIFNR", "BANKL", "BANKN"]], on="LIFNR", how="left")
vv["spend"] = vv["LIFNR"].map(spend).fillna(0)


def gst_ok(g):
    C = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if not isinstance(g, str) or not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", g):
        return False
    f, t = 2, 0
    for ch in reversed(g[:14]):
        d = f * C.index(ch); f = 1 if f == 2 else 2; t += d // 36 + d % 36
    return C[(36 - t % 36) % 36] == g[14]


vv["gst_valid"] = vv["STCD3"].map(gst_ok)
vv["completeness"] = vv[["STRAS", "PSTLZ", "TELF1", "SMTP_ADDR", "STCD3", "BANKN"]].notna().sum(axis=1)
vv = vv.sort_values(["cluster_id", "gst_valid", "spend", "completeness", "ERDAT"], ascending=[True, False, False, False, True])
vv["is_survivor"] = ~vv.duplicated("cluster_id")
golden_v = []
zterm_mode = lfb1.merge(clus_v, on="LIFNR").groupby("cluster_id")["ZTERM"].agg(mode)
for cid, g in vv[vv.groupby("cluster_id")["LIFNR"].transform("size") > 1].groupby("cluster_id"):
    s = g.iloc[0]
    banks = g["BANKN"].dropna().unique()
    name = re.sub(r"^M/s\s+", "", s.NAME1, flags=re.I)
    golden_v.append(dict(
        golden_id=f"GV{cid}", survivor_lifnr=s.LIFNR, members=len(g), NAME1=name.title() if name.isupper() else name,
        STCD3=mode(g.loc[g.gst_valid, "STCD3"]), ORT01=std_city(s.ORT01).title(),
        PSTLZ=s.PSTLZ if pd.notna(s.PSTLZ) else mode(g.PSTLZ), TELF1=s.TELF1 if pd.notna(s.TELF1) else mode(g.TELF1),
        SMTP_ADDR=(s.SMTP_ADDR if pd.notna(s.SMTP_ADDR) else mode(g.SMTP_ADDR)),
        BANKN=banks[0] if len(banks) == 1 else s.BANKN,
        bank_conflict=len(banks) > 1, ZTERM=zterm_mode.get(cid), combined_spend_inr=round(g.spend.sum(), 0),
        control_note="BANK CONFLICT - call-back verification before merge" if len(banks) > 1 else ""))
golden_v = pd.DataFrame(golden_v)
xref_v = vv[["LIFNR", "cluster_id", "is_survivor"]].copy()
xref_v["golden_lifnr"] = xref_v["cluster_id"].map(vv[vv.is_survivor].set_index("cluster_id")["LIFNR"])

# =============================================================================
# 5. Persist
# =============================================================================
clus_m.assign(cluster_size=clus_m.groupby("cluster_id")["MATNR"].transform("size")).to_parquet(PROCESSED / "er_material_clusters.parquet", index=False)
clus_v.assign(cluster_size=clus_v.groupby("cluster_id")["LIFNR"].transform("size")).to_parquet(PROCESSED / "er_vendor_clusters.parquet", index=False)
rq_m.to_parquet(PROCESSED / "er_material_review_queue.parquet", index=False)
rq_v.to_parquet(PROCESSED / "er_vendor_review_queue.parquet", index=False)
golden_m.to_parquet(PROCESSED / "golden_material.parquet", index=False)
golden_v.to_parquet(PROCESSED / "golden_vendor.parquet", index=False)
merge_plan.to_parquet(PROCESSED / "merge_plan_material.parquet", index=False)
xref_m.to_parquet(PROCESSED / "xref_material.parquet", index=False)
xref_v.to_parquet(PROCESSED / "xref_vendor.parquet", index=False)
pd.DataFrame(curve).to_csv(REPORTS / "er_threshold_curve.csv", index=False)

def pair_block(sp):      # pairwise ER accuracy - a DIFFERENT question from DQ rule precision/recall
    return dict(threshold=sp["threshold"], pair_tp=sp["tp"], pair_fp=sp["fp"], pair_fn=sp["fn"],
                pred_pairs=sp["pred_pairs"], true_pairs=sp["true_pairs"],
                pair_precision=sp["precision"], pair_recall=sp["recall"], pair_f1=sp["f1"])


def golden_block(xref):   # what survivorship produced
    multi = xref[xref.groupby("cluster_id")["cluster_id"].transform("size") > 1]
    return dict(cluster_count=int(multi.cluster_id.nunique()), survivor_count=int(multi.is_survivor.sum()),
                retired_count=int((~multi.is_survivor).sum()), records_in_clusters=len(multi))


metrics = dict(
    definitions=dict(
        pair_metrics="Pairwise: every pair of records the model says are the same entity vs every truly-same pair.",
        golden_metrics="cluster_count = entities with 2+ records; survivor_count = records kept; retired_count = records to merge away.",
        dq_metrics="Record-level rule metrics (M10/V07) are in dbt model dq_reconciliation, basis dup_surplus."),
    material=dict(pairs=pair_block(best_m), baseline_fuzzy90=base_m_s, bands=bands["material"],
                  golden=golden_block(xref_m),
                  stock_in_retired_records_inr=float(merge_plan["stock_to_transfer_inr"].sum()) if len(merge_plan) else 0),
    vendor=dict(pairs=pair_block(best_v), baseline_fuzzy90=base_v_s, bands=bands["vendor"],
                golden=golden_block(xref_v),
                bank_conflicts=int(golden_v["bank_conflict"].sum()) if len(golden_v) else 0),
)
(REPORTS / "er_metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
print(json.dumps(metrics, indent=2, default=str))
