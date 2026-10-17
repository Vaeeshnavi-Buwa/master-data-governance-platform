"""
Project configuration: plants, owners, rule catalogue, severities and programme dates.
"""
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"
DB_PATH = ROOT / "data" / "mdg.duckdb"

SEED = 20260927

# --- Timeline -------------------------------------------------------------
SNAPSHOT_DATE = date(2026, 9, 27)      # "today" - date of the current SAP extract
WINDOW_START = date(2025, 10, 1)       # start of the 12-month DQ history
PROGRAM_START = date(2026, 4, 1)       # governance program go-live (council, workflow, stewards)

# --- Organisation ----------------------------------------------------------
# 8 plants across 6 company codes. cross_border = plant imports/exports, so
# HS code + country of origin are mandatory (customs).
PLANTS = {
    "IN10": dict(name="Pune (Chakan)",     bukrs="1000", country="IN", region="India", cross_border=True),
    "IN20": dict(name="Silvassa",          bukrs="1000", country="IN", region="India", cross_border=False),
    "IN30": dict(name="Chennai",           bukrs="1000", country="IN", region="India", cross_border=True),
    "TH10": dict(name="Rayong",            bukrs="2000", country="TH", region="APAC",  cross_border=True),
    "PL10": dict(name="Poznan",            bukrs="3000", country="PL", region="Europe", cross_border=True),
    "DE10": dict(name="Neuss",             bukrs="3100", country="DE", region="Europe", cross_border=True),
    "US10": dict(name="Columbus OH",       bukrs="4000", country="US", region="Americas", cross_border=False),
    "MX10": dict(name="Queretaro",         bukrs="5000", country="MX", region="Americas", cross_border=True),
}
COMPANY_CODES = {"1000": "IN", "2000": "TH", "3000": "PL", "3100": "DE", "4000": "US", "5000": "MX"}

# Material types (SAP MTART) and their share of the material master
MTART_MIX = {"ROH": 0.30, "HALB": 0.15, "FERT": 0.30, "ERSA": 0.15, "HIBE": 0.05, "VERP": 0.05}

# Owning business function per rule
OWNER_FUNCTIONS = [
    "Product Data (PLM)", "Commercial", "Supply Planning", "Procurement",
    "Finance", "Trade Compliance", "Indirect Tax",
]

SEVERITY_WEIGHT = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

# --- DQ rule catalogue -------------------------------------------------------
# p_backlog = share of applicable legacy records that carry the defect at the
# start of the window. The generator uses it; dbt never sees it.
RULES = [
    # id,   domain,     table,  dimension,     severity,  owner,               p_backlog, description,                                                   cost_driver
    ("M01", "Material", "MARA", "Completeness", "High",    "Product Data (PLM)", 0.040, "Material group (MATKL) missing",                                 "spend_visibility"),
    ("M02", "Material", "MARA", "Consistency",  "Medium",  "Product Data (PLM)", 0.030, "Net weight greater than gross weight",                           "compliance_holds"),
    ("M03", "Material", "MARA", "Completeness", "Medium",  "Product Data (PLM)", 0.020, "Weight maintained without weight unit (GEWEI)",                  "compliance_holds"),
    ("M04", "Material", "MARA", "Validity",     "High",    "Product Data (PLM)", 0.030, "Base unit of measure not allowed for material group",            "wrong_orders"),
    ("M05", "Material", "MAKT", "Validity",     "Low",     "Product Data (PLM)", 0.050, "Description violates naming convention",                         "none"),
    ("M06", "Material", "MAKT", "Completeness", "High",    "Product Data (PLM)", 0.015, "English description (SPRAS=E) missing",                          "none"),
    ("M07", "Material", "MARA", "Completeness", "High",    "Commercial",         0.080, "Finished good without product hierarchy (PRDHA)",                "launch_delays"),
    ("M08", "Material", "MARA", "Validity",     "High",    "Commercial",         0.050, "Finished good EAN/GTIN missing or check digit invalid",          "launch_delays"),
    ("M09", "Material", "MARA", "Consistency",  "Critical","Finance",            0.015, "Flagged for deletion but stock on hand",                         "stranded_stock"),
    ("M10", "Material", "MARA", "Uniqueness",   "Critical","Product Data (PLM)", None,  "Duplicate material (probabilistic match)",                       "duplicate_stock"),
    ("P01", "Plant",    "MARC", "Consistency",  "High",    "Supply Planning",    0.020, "Bought-in material set to in-house production (BESKZ=E)",        "wrong_orders"),
    ("P02", "Plant",    "MARC", "Consistency",  "High",    "Supply Planning",    0.080, "Reorder-point MRP (VB) with reorder point = 0",                  "stockouts"),
    ("P03", "Plant",    "MARC", "Validity",     "High",    "Procurement",        0.040, "Planned delivery time 0 or >180 days on external procurement",   "wrong_orders"),
    ("P04", "Plant",    "MARC", "Completeness", "Medium",  "Supply Planning",    0.030, "MRP-planned material without MRP controller",                    "wrong_orders"),
    ("P05", "Plant",    "MARC", "Completeness", "Critical","Trade Compliance",   0.090, "HS code or country of origin missing at cross-border plant",     "compliance_holds"),
    ("P06", "Plant",    "MBEW", "Validity",     "Critical","Finance",            0.015, "Standard price = 0 with stock on hand",                          "valuation"),
    ("P07", "Plant",    "MBEW", "Accuracy",     "High",    "Finance",            0.020, "Price >10x or <0.1x material-group median",                      "valuation"),
    ("P08", "Plant",    "MARC", "Consistency",  "Medium",  "Supply Planning",    0.020, "Plant status active while cross-plant status blocked",           "wrong_orders"),
    ("V01", "Vendor",   "LFA1", "Completeness", "Critical","Indirect Tax",       0.060, "Indian vendor without GSTIN",                                    "gst_itc"),
    ("V02", "Vendor",   "LFA1", "Validity",     "Critical","Indirect Tax",       0.040, "GSTIN invalid (format, checksum or state mismatch)",             "gst_itc"),
    ("V03", "Vendor",   "LFA1", "Validity",     "Medium",  "Procurement",        0.030, "Postal code missing or invalid for country",                     "none"),
    ("V04", "Vendor",   "LFB1", "Completeness", "High",    "Finance",            0.040, "Payment terms (ZTERM) missing in company code",                  "none"),
    ("V05", "Vendor",   "LFBK", "Consistency",  "Critical","Finance",            0.005, "Bank account shared by unrelated vendors",                       "fraud_exposure"),
    ("V06", "Vendor",   "LFA1", "Completeness", "Low",     "Procurement",        0.050, "No phone and no email",                                          "none"),
    ("V07", "Vendor",   "LFA1", "Uniqueness",   "Critical","Procurement",        None,  "Duplicate vendor (probabilistic match)",                         "duplicate_payments"),
    ("V08", "Vendor",   "LFA1", "Consistency",  "Medium",  "Procurement",        0.015, "Posting-blocked vendor with spend in last 12 months",            "none"),
]
RULE_COLS = ["rule_id", "domain", "table_name", "dimension", "severity", "owner_function",
             "p_backlog", "description", "cost_driver"]

# Monthly probability that an open defect gets fixed.
# Before the program: ad-hoc fixing. After: stewards work a prioritised queue.
HAZARD_PRE = 0.004
HAZARD_POST = {"Critical": 0.18, "High": 0.12, "Medium": 0.08, "Low": 0.03}
# Preventive controls (create-workflow validation, search-before-create)
# cut the defect rate on NEW records to this share after go-live.
PREVENTION_FACTOR = 0.35
