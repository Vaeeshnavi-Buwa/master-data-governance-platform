"""
Build the dashboard as one self-contained HTML file.

Reads the dbt marts and the ER/cost reports, injects them as JSON into dashboard/template.html.
  dashboard/mdg_dashboard.html   page body only
  dashboard/standalone.html      full page, open locally
"""
import json

import duckdb
import pandas as pd

from config import DB_PATH, PLANTS, REPORTS, ROOT

con = duckdb.connect(str(DB_PATH), read_only=True)
q = lambda s: con.sql(s).df()

trend = q("select month_end::varchar m, dq_score s from marts.mart_dq_trend_scores where slice_type='overall' order by 1")
trend_dom = q("select month_end::varchar m, slice_value d, dq_score s from marts.mart_dq_trend_scores where slice_type='domain' order by 1, 2")
health = q("select month_end::varchar m, entity e, fit_for_use_rate r, records, records_with_defects from marts.mart_record_health order by 1")
heat = q("""select slice_value org, domain, dq_score s, failures from marts.mart_dq_scorecard
            where slice_type='org_unit_x_domain' and slice_value in (select org_unit from reference.org_units where org_type='plant')
            order by 1, 2""")
owners = q("""select s.slice_value as "owner", s.dq_score s, s.failures,
                     d.data_owner_role as "role"
              from marts.mart_dq_scorecard s left join reference.data_owners d on d.owner_function = s.slice_value
              where slice_type='owner_function' order by s.dq_score""")
sla = q("""select owner_function as "owner", sum(open_exceptions) as "open", sum(case when is_legacy_backlog then open_exceptions else 0 end) legacy,
                  sum(case when not is_legacy_backlog then open_exceptions else 0 end) new_open,
                  sum(case when not is_legacy_backlog then sla_breached else 0 end) new_breached
           from marts.mart_sla_by_owner group by 1""")
rules = q("""select m.*, c.description, c.table_name, c.dimension, c.severity, c.owner_function, c.detection_method
             from marts.mart_rule_metrics m join reference.dq_rule_catalog c using (rule_id) order by rule_id""")
cost_rule = pd.read_csv(REPORTS / "cost_by_rule.csv")
cost_driver = pd.read_csv(REPORTS / "cost_by_driver.csv")
cost_org = pd.read_csv(REPORTS / "cost_by_org_unit.csv")
cost = json.loads((REPORTS / "cost_summary.json").read_text())
er = json.loads((REPORTS / "er_metrics.json").read_text())
gx = json.loads((REPORTS / "gx_summary.json").read_text())
counts = {t: int(q(f"select count(*) c from staging.stg_{t}").c[0]) for t in ["mara", "marc", "makt", "mbew", "lfa1", "lfb1", "lfbk"]}
golden = q("select * from read_parquet('" + str(ROOT / "data/processed/golden_vendor.parquet") + "') where members > 1 limit 1")
xm = q("""select g.golden_id, g.survivor_matnr, g.MAKTX, g.members, g.plants_union, g.total_stock_value
          from read_parquet('""" + str(ROOT / "data/processed/golden_material.parquet") + """') g
          order by g.total_stock_value desc limit 1""")
xm_members = q("""select m.matnr, t.maktx, m.home_plant, m.created_on::varchar created, x.is_survivor
                  from staging.stg_er_material x join staging.stg_mara m using (matnr)
                  left join staging.stg_makt t on t.matnr = m.matnr and t.spras='E'
                  where x.golden_matnr = '""" + xm.survivor_matnr[0] + "' order by x.is_survivor desc")

rules = rules.merge(cost_rule[["rule_id", "annual_cost_inr"]], on="rule_id", how="left")
data = dict(
    meta=dict(snapshot="2026-09-27", program_start="2026-04", counts=counts, total_records=sum(counts.values()),
              plants={k: v["name"] for k, v in PLANTS.items()}, gx_gate=gx["pipeline_gate"],
              gx_checks=len(gx["results"])),
    trend=trend.to_dict("records"), trend_dom=trend_dom.to_dict("records"), health=health.to_dict("records"),
    heat=heat.to_dict("records"), owners=owners.merge(sla, on="owner", how="left").to_dict("records"),
    rules=rules.fillna({"annual_cost_inr": 0}).to_dict("records"),
    cost=cost, cost_driver=cost_driver.to_dict("records"), cost_org=cost_org.to_dict("records"),
    er=er, golden_material=dict(head=xm.to_dict("records")[0], members=xm_members.to_dict("records")),
)
blob = json.dumps(data, default=str)
tpl = (ROOT / "dashboard" / "template.html").read_text()
page = tpl.replace("/*__DATA__*/null", blob)
(ROOT / "dashboard" / "mdg_dashboard.html").write_text(page)
(ROOT / "dashboard" / "standalone.html").write_text(
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    '</head><body>' + page + "</body></html>")
print("dashboard written:", len(page) // 1024, "KB")
print(json.dumps({k: data["meta"][k] for k in ["total_records", "gx_gate"]}))

