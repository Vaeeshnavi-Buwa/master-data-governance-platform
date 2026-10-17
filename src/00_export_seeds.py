"""
Export reference data from config.py to dbt seed CSVs.
Rule and owner changes go through config, so the git history doubles as the change log.
"""
import csv
from pathlib import Path

from config import PLANTS, COMPANY_CODES, RULES, RULE_COLS, SEVERITY_WEIGHT, ROOT

SEEDS = ROOT / "dbt_mdg" / "seeds"
SEEDS.mkdir(parents=True, exist_ok=True)


def write(name, header, rows):
    with open(SEEDS / f"{name}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


write("dq_rule_catalog",
      ["rule_id", "domain", "table_name", "dimension", "severity", "severity_weight", "owner_function",
       "description", "cost_driver", "detection_method"],
      [[r[0], r[1], r[2], r[3], r[4], SEVERITY_WEIGHT[r[4]], r[5], r[7], r[8],
        "probabilistic_er" if r[0] in ("M10", "V07", "V05") else "deterministic"] for r in RULES])

rows = [[p, "plant", v["name"], v["country"], v["region"], v["bukrs"], str(v["cross_border"]).lower()] for p, v in PLANTS.items()]
rows += [[b, "company_code", f"Company code {b}", c, {"IN": "India", "TH": "APAC", "PL": "Europe", "DE": "Europe",
                                                      "US": "Americas", "MX": "Americas"}[c], b, "false"]
         for b, c in COMPANY_CODES.items()]
write("org_units", ["org_unit", "org_type", "org_name", "country", "region", "bukrs", "cross_border"], rows)

ALLOWED = {"RM-FILM": ["KG"], "RM-RESIN": ["KG"], "RM-INK": ["KG", "L"], "RM-ADH": ["KG"], "RM-BOARD": ["KG"],
           "RM-FOIL": ["KG"], "SF-PRINT": ["KG", "M"], "SF-LAM": ["KG", "M"], "FG-POUCH": ["EA", "TH"],
           "FG-CARTON": ["EA", "TH"], "FG-ROLL": ["KG", "M"], "FG-TUBE": ["EA", "TH"], "SP-BRG": ["EA", "SET"],
           "SP-BLADE": ["EA", "SET"], "SP-ANLX": ["EA"], "SP-MOTOR": ["EA"], "SP-SENSOR": ["EA"],
           "SP-PART": ["EA", "SET"], "OS-CHEM": ["L", "KG"], "OS-CONS": ["EA", "PAK"], "PK-PALLET": ["EA"],
           "PK-BOX": ["EA"], "PK-STRETCH": ["KG", "ROL"], "PK-CORE": ["EA"]}
write("material_group_uom", ["matkl", "allowed_uom"], [[k, u] for k, us in ALLOWED.items() for u in us])

write("india_gst_states", ["regio", "gst_state_code", "state_name"], [
    ["MH", "27", "Maharashtra"], ["GJ", "24", "Gujarat"], ["DH", "26", "Dadra & Nagar Haveli and Daman & Diu"],
    ["TN", "33", "Tamil Nadu"], ["KA", "29", "Karnataka"], ["DL", "07", "Delhi"], ["HR", "06", "Haryana"],
    ["UP", "09", "Uttar Pradesh"], ["TS", "36", "Telangana"], ["WB", "19", "West Bengal"], ["HP", "02", "Himachal Pradesh"]])

write("postal_formats", ["land1", "regex"], [
    ["IN", r"^[1-9][0-9]{5}$"], ["PL", r"^[0-9]{2}-[0-9]{3}$"], ["DE", r"^[0-9]{5}$"], ["TH", r"^[0-9]{5}$"],
    ["US", r"^[0-9]{5}(-[0-9]{4})?$"], ["MX", r"^[0-9]{5}$"]])

write("data_owners", ["owner_function", "data_owner_role", "escalation_to"], [
    ["Product Data (PLM)", "Head of R&D / PLM", "VP Operations"],
    ["Commercial", "Head of Sales Operations", "VP Sales"],
    ["Supply Planning", "Head of Supply Chain Planning", "VP Supply Chain"],
    ["Procurement", "Head of Procurement", "CPO"],
    ["Finance", "Financial Controller", "CFO"],
    ["Trade Compliance", "Head of EXIM / Trade Compliance", "CFO"],
    ["Indirect Tax", "Head of Indirect Tax", "CFO"]])
print("seeds written to", SEEDS)
