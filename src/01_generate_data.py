"""
Generate a synthetic SAP material and vendor master with injected defects.

SAP data can't be published, so the extract is generated. Every injected defect is
written to a defect ledger, which lets each rule and matching model be scored for
precision and recall.

Tables: MARA, MARC, MAKT, MBEW, LFA1, LFB1, LFBK
Extras: usage_12m (stand-in for MSEG), vendor_spend_12m (stand-in for EKKO/EKPO),
        truth tables and the defect ledger (not visible to the dbt rules)

Run: python src/01_generate_data.py
"""
from __future__ import annotations

import random
import string
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd

from reference_data import std_vendor_name
from config import (HAZARD_POST, HAZARD_PRE, PLANTS, COMPANY_CODES, PREVENTION_FACTOR,
                    PROGRAM_START, RAW, RULES, RULE_COLS, SEED, SNAPSHOT_DATE, WINDOW_START)

rng = np.random.default_rng(SEED)
random.seed(SEED)
RAW.mkdir(parents=True, exist_ok=True)

N_MATERIALS = 48_000        # true, distinct materials
N_VENDORS = 11_500          # true, distinct vendors
MAT_DUP_RATE = 0.085        # share of legacy materials that got duplicated at least once
VEN_DUP_RATE = 0.12
HAZARD_POST_DUP = 0.07      # merging duplicates is slow (stock, BOMs, info records)

PLANT_IDS = list(PLANTS)
PLANT_W = np.array([.22, .14, .15, .10, .10, .10, .10, .09])
LOCAL_LANG = {"DE10": "D", "PL10": "L", "TH10": "2", "MX10": "S"}   # SAP language keys

# =============================================================================
# Helpers
# =============================================================================
def rdate(start: date, end: date) -> date:
    return start + timedelta(days=int(rng.integers(0, max(1, (end - start).days + 1))))


def creation_date() -> date:
    """8% of records created inside the 12-month window, rest spread 2008..window,
    skewed to recent years (the business grew)."""
    if rng.random() < 0.08:
        return rdate(WINDOW_START, SNAPSHOT_DATE - timedelta(days=1))
    year = int(rng.choice(np.arange(2008, 2026), p=_year_w))
    d = rdate(date(year, 1, 1), date(year, 12, 31))
    return min(d, WINDOW_START - timedelta(days=1))


_year_w = np.linspace(1, 3, 18)
_year_w = _year_w / _year_w.sum()


def ean13(prefix12: str) -> str:
    s = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(prefix12))
    return prefix12 + str((10 - s % 10) % 10)


GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gst_checksum(g14: str) -> str:
    factor, total = 2, 0
    for ch in reversed(g14):
        d = factor * GST_CHARS.index(ch)
        factor = 1 if factor == 2 else 2
        total += d // 36 + d % 36
    return GST_CHARS[(36 - total % 36) % 36]


assert gst_checksum("27AAPFU0939F1Z") == "V"   # public example GSTIN


def month_starts():
    m, out = WINDOW_START, []
    while m <= SNAPSHOT_DATE:
        out.append(m)
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return out


MONTHS = month_starts()


def resolve_date(injected: date, severity: str, dup: bool = False):
    """Simulate when an open defect is fixed (None = still open today)."""
    start = max(injected, WINDOW_START)
    for ms in MONTHS:
        me = min(date(ms.year + (ms.month == 12), ms.month % 12 + 1, 1) - timedelta(days=1),
                 SNAPSHOT_DATE - timedelta(days=1))
        if me < start:
            continue
        if ms < PROGRAM_START:
            h = HAZARD_PRE
        else:
            h = HAZARD_POST_DUP if dup else HAZARD_POST[severity]
        if rng.random() < h:
            return rdate(max(start, ms), me)
    return None


def defect_injected(created: date, p: float):
    """Decide if a record created on `created` carries a defect; return inject date."""
    if created < WINDOW_START:
        return rdate(created, WINDOW_START - timedelta(days=1)) if rng.random() < p else None
    factor = 1.0 if created < PROGRAM_START else PREVENTION_FACTOR
    return created if rng.random() < p * factor else None


RULE = {r[0]: dict(zip(RULE_COLS, r)) for r in RULES}
ledger: list[dict] = []


def log(rule_id, key, plant, injected, resolved):
    ledger.append(dict(rule_id=rule_id, record_key=key, plant=plant,
                       injected_date=injected, resolved_date=resolved))


# =============================================================================
# 1. Material catalogue (flexible packaging)
# =============================================================================
SUBS = {"BOPP": [12, 15, 18, 20, 25, 30, 35, 40], "PET": [10, 12, 15, 19, 23, 36],
        "CPP": [20, 25, 30, 40, 50], "LDPE": [30, 40, 50, 60, 70, 80, 90, 100], "NYLON": [12, 15, 20, 25]}
FINISH = ["PLAIN", "MET", "MATT", "HS", "CORONA", "WHITE"]
STRUCTS = ["PET12/PE50", "PET12/AL9/PE60", "BOPP20/BOPP20", "PET12/MET/PE40", "BOPP18/MET/CPP25",
           "PET12/NY15/PE80", "PAPER40/PE20", "PET12/AL7/PE50", "BOPP25/PE40", "PET10/CPP30"]
POUCH_STRUCT = ["PET/PE", "PET/MET/PE", "BOPP/BOPP", "PET/AL/PE", "PET/NY/PE"]
MAKES = ["SKF", "FAG", "NSK", "NTN", "TIMKEN"]
EL_MAKES = ["SIEMENS", "ABB", "SCHNEIDER", "OMRON", "SICK", "IFM"]

# HS codes (8-digit ITC-HS style) per material group
HS = {"RM-FILM": "39202090", "RM-RESIN": "39011010", "RM-INK": "32151990", "RM-ADH": "35069190",
      "RM-BOARD": "48109200", "RM-FOIL": "76071190", "SF-PRINT": "39219099", "SF-LAM": "39219099",
      "FG-POUCH": "39232990", "FG-CARTON": "48191010", "FG-ROLL": "39219099", "FG-TUBE": "39233090",
      "SP-BRG": "84821011", "SP-BLADE": "82089090", "SP-ANLX": "84439990", "SP-MOTOR": "85015290",
      "SP-SENSOR": "85365090", "SP-PART": "84439990", "OS-CHEM": "29153100", "OS-CONS": "40151900",
      "PK-PALLET": "44152000", "PK-BOX": "48191090", "PK-STRETCH": "39201012", "PK-CORE": "48221000"}

ALLOWED_UOM = {"RM-FILM": ["KG"], "RM-RESIN": ["KG"], "RM-INK": ["KG", "L"], "RM-ADH": ["KG"],
               "RM-BOARD": ["KG"], "RM-FOIL": ["KG"], "SF-PRINT": ["KG", "M"], "SF-LAM": ["KG", "M"],
               "FG-POUCH": ["EA", "TH"], "FG-CARTON": ["EA", "TH"], "FG-ROLL": ["KG", "M"],
               "FG-TUBE": ["EA", "TH"], "SP-BRG": ["EA", "SET"], "SP-BLADE": ["EA", "SET"],
               "SP-ANLX": ["EA"], "SP-MOTOR": ["EA"], "SP-SENSOR": ["EA"], "SP-PART": ["EA", "SET"],
               "OS-CHEM": ["L", "KG"], "OS-CONS": ["EA", "PAK"], "PK-PALLET": ["EA"],
               "PK-BOX": ["EA"], "PK-STRETCH": ["KG", "ROL"], "PK-CORE": ["EA"]}
ALL_UOM = ["EA", "KG", "M", "L", "M2", "PAK", "TH", "SET", "ROL"]

design_pool: list[int] = []


_code_pool = iter(rng.permutation(np.arange(10000, 99999)))   # unique 5-digit codes (designs, part numbers)


def new_design() -> int:
    d = int(next(_code_pool))
    design_pool.append(d)
    return d


def ch(x):
    return x[int(rng.integers(len(x)))]


def make_material(mtart: str) -> dict:
    """Return canonical attributes for one material of type mtart."""
    m = dict(MFRPN=None, MFRNR=None, EAN11=None, PRDHA=None)
    if mtart == "ROH":
        g = ch(["RM-FILM"] * 4 + ["RM-RESIN", "RM-INK", "RM-INK", "RM-ADH", "RM-BOARD", "RM-FOIL"])
        if g == "RM-FILM":
            s = ch(list(SUBS)); d = f"FILM {s} {ch(FINISH)} {ch(SUBS[s])}MIC {int(rng.integers(30, 161)) * 10}MM"
            price = (120, 350)
        elif g == "RM-RESIN":
            d = f"RESIN {ch(['LLDPE','LDPE','HDPE','PP','EVOH','MLLDPE'])} {ch(['FILM GRADE','BLOWN','CAST','COEX'])} MFI {ch([0.5,0.8,1,2,3,4.5,7,12])} G{rng.integers(100,999)}"
            price = (90, 160)
        elif g == "RM-INK":
            col = ch(["CYAN", "MAGENTA", "YELLOW", "BLACK", "WHITE", f"PMS {rng.integers(100, 7700)}"])
            d = f"INK {ch(['SOLV PU','SOLV NC','WATER BASED','UV FLEXO'])} {col} S{rng.integers(100,999)}"
            price = (250, 600)
        elif g == "RM-ADH":
            d = f"ADHESIVE {ch(['PU SOLVENTLESS','PU SOLVENT','WATER BASED','HOTMELT'])} {ch(['1K','2K'])} A{rng.integers(100,999)}"
            price = (300, 500)
        elif g == "RM-BOARD":
            d = f"BOARD {ch(['FBB','SBS','WLC','KRAFT','DUPLEX'])} {int(rng.integers(20, 46)) * 10}GSM {ch(['700X1000','720X1020','640X900','790X1090','560X760'])}"
            price = (60, 90)
        else:
            d = f"FOIL ALU {ch([6,7,9,12,20,30,40])}MIC {int(rng.integers(30, 161)) * 10}MM {ch(['SOFT','HARD'])}"
            price = (450, 650)
        meins, w = "KG", (1.0, 1.05)
    elif mtart == "HALB":
        if rng.random() < 0.5:
            g = "SF-PRINT"; s = ch(list(SUBS))
            dsg = ch(design_pool) if design_pool and rng.random() < 0.4 else new_design()
            d = f"PRINTED ROLL {s} {ch(SUBS[s])}MIC D{dsg}"
        else:
            g = "SF-LAM"; d = f"LAMINATE {ch(STRUCTS)} D{new_design()}"
        meins, w, price = "KG", (1.0, 1.04), (250, 520)
    elif mtart == "FERT":
        g = ch(["FG-POUCH"] * 4 + ["FG-CARTON", "FG-CARTON", "FG-ROLL", "FG-ROLL", "FG-TUBE"])
        dsg = new_design()
        if g == "FG-POUCH":
            d = f"POUCH {ch(['SUP','3SS','CS','ZIP','SPOUT'])} {ch(POUCH_STRUCT)} {ch([5,10,20,50,100,200,250,500,1000])}G D{dsg}"
            meins, w, price = "EA", (0.004, 0.0046), (1.5, 12)
        elif g == "FG-CARTON":
            d = f"CARTON {ch(['MONO','TUCK END','CRASH LOCK','SLEEVE'])} {int(rng.integers(20, 46)) * 10}GSM D{dsg}"
            meins, w, price = "EA", (0.02, 0.022), (3, 20)
        elif g == "FG-ROLL":
            d = f"LAMINATE ROLL {ch(STRUCTS)} {int(rng.integers(30, 131)) * 10}MM D{dsg}"
            meins, w, price = "KG", (1.0, 1.05), (300, 600)
        else:
            d = f"TUBE LAMI {ch(['ABL','PBL'])} {ch([19,22,25,28,30,35,40,50])}MM D{dsg}"
            meins, w, price = "EA", (0.008, 0.009), (4, 15)
        m["EAN11"] = ean13("890" + "".join(str(x) for x in rng.integers(0, 10, 9)))
        m["PRDHA"] = f"01{rng.integers(1, 9):03d}{rng.integers(1, 60):04d}"
    elif mtart == "ERSA":
        g = ch(["SP-BRG", "SP-BLADE", "SP-ANLX", "SP-MOTOR", "SP-SENSOR"] + ["SP-PART"] * 5)
        if g == "SP-BRG":
            code = f"{ch([62, 63])}{rng.integers(0, 31):02d}-{ch(['2RS','ZZ','C3','2RSC3'])}"
            mk = ch(MAKES); d = f"BEARING {code} {mk}"; m.update(MFRPN=code, MFRNR=mk); w = (0.2, 0.25)
        elif g == "SP-BLADE":
            d = f"DOCTOR BLADE {int(rng.integers(4, 13)) * 5}X{ch(['0.10','0.15','0.20'])} {ch(['STEEL','CERAMIC TIP','PLASTIC'])} B{rng.integers(100,999)}"; w = (0.1, 0.12)
        elif g == "SP-ANLX":
            d = f"SLEEVE ANILOX {int(rng.integers(20, 121)) * 10}LPI {ch([2,3,4,5,6,8])}BCM {int(rng.integers(80, 161)) * 10}MM"; w = (12, 14)
        elif g == "SP-MOTOR":
            mk = ch(EL_MAKES); pn = f"{mk[:2]}{rng.integers(100000, 999999)}"
            d = f"MOTOR AC {ch([0.37,0.75,1.5,2.2,3.7,5.5,7.5,11,15])}KW {ch([960,1440,2880])}RPM {mk}"
            m.update(MFRPN=pn, MFRNR=mk); w = (15, 18)
        elif g == "SP-SENSOR":
            mk = ch(EL_MAKES); pn = f"{mk[:2]}{rng.integers(100000, 999999)}"
            d = f"SENSOR {ch(['PROX','PHOTO','ENCODER','TEMP'])} M{ch([8,12,18,30])} {mk} {pn[-4:]}"
            m.update(MFRPN=pn, MFRNR=mk); w = (0.1, 0.15)
        else:
            pn = f"P{next(_code_pool)}"
            d = f"SPARE {ch(['ROTO','LAMINATOR','SLITTER','POUCHER','EXTRUDER'])} {ch(['ROLLER','SHAFT','SEAL','BUSH','SPRING','VALVE','CYLINDER','BELT','GEAR','NOZZLE'])} {pn}"
            m.update(MFRPN=pn, MFRNR="OEM"); w = (0.5, 0.6)
        meins, price = "EA", None
    elif mtart == "HIBE":
        if rng.random() < 0.3:
            g = "OS-CHEM"
            d = f"SOLVENT {ch(['ETHYL ACETATE','IPA','NPA','MEK','TOLUENE','ACETONE'])} {ch([95,98,99,99.5,99.9])}PCT {ch([20,50,200])}L"
            meins, w, price = "L", (0.9, 1.0), (80, 180)
        else:
            g = "OS-CONS"
            d = f"CONSUMABLE {ch(['GLOVES NITRILE','TAPE MASKING','CLOTH LINT FREE','BRUSH','CUTTER BLADE','MARKER','CABLE TIE'])} C{rng.integers(1000, 9999)}"
            meins, w, price = "EA", (0.05, 0.06), (20, 400)
    else:  # VERP
        g = ch(["PK-PALLET", "PK-BOX", "PK-BOX", "PK-STRETCH", "PK-CORE"])
        if g == "PK-PALLET":
            pd_ = sorted([ch([800, 1000, 1100, 1140, 1200]), ch([800, 1000, 1100, 1200])], reverse=True)
            d = f"PALLET {ch(['WOOD','PLASTIC'])} {pd_[0]}X{pd_[1]} {ch(['HT','NON HT','4WAY'])}"
            meins, w, price = "EA", (18, 20), (800, 1500)
        elif g == "PK-BOX":
            dims = sorted([int(rng.integers(20, 81)) * 10, int(rng.integers(20, 61)) * 10, int(rng.integers(15, 61)) * 10], reverse=True)
            d = f"CORRUGATED BOX {ch([3,5,7])}PLY {dims[0]}X{dims[1]}X{dims[2]}"
            meins, w, price = "EA", (0.5, 0.6), (25, 120)
        elif g == "PK-STRETCH":
            d = f"STRETCH FILM {ch([17,20,23,25,30])}MIC {ch([450,500,750])}MM"
            meins, w, price = "KG", (1.0, 1.08), (130, 170)
        else:
            d = f"CORE PAPER {ch([3,6])}IN {int(rng.integers(30, 171)) * 10}MM"
            meins, w, price = "EA", (0.8, 0.9), (40, 160)
    m.update(MATKL=g, MAKTX=d[:40].rstrip(), MEINS=meins, NTGEW=round(w[0], 4), BRGEW=round(w[1], 4),
             GEWEI="KG", STAWN=HS[g], price_range=price)
    return m


# ---- build distinct materials -------------------------------------------------
print("Generating materials ...")
mtarts = rng.choice(list({"ROH": 0, "HALB": 0, "FERT": 0, "ERSA": 0, "HIBE": 0, "VERP": 0}),
                    size=N_MATERIALS, p=[.30, .15, .30, .15, .05, .05])
seen, mats = set(), []
num_range = {"ROH": 10_000_000, "HALB": 20_000_000, "FERT": 30_000_000,
             "ERSA": 40_000_000, "HIBE": 50_000_000, "VERP": 60_000_000}
counter = defaultdict(int)
for i, mt in enumerate(mtarts):
    for _ in range(20):
        m = make_material(mt)
        if m["MAKTX"] not in seen:
            break
    seen.add(m["MAKTX"])
    m["MTART"] = mt
    m["entity_id"] = f"MAT-E{i:06d}"
    m["ERSDA"] = creation_date()
    mats.append(m)


def plants_for(mt: str) -> list[str]:
    k = {"FERT": ch([1, 1, 1, 2, 2, 3]), "HALB": ch([1, 1, 2]), "ROH": int(rng.integers(2, 8)),
         "ERSA": int(rng.integers(1, 5)), "HIBE": int(rng.integers(3, 9)), "VERP": int(rng.integers(3, 9))}[mt]
    return list(rng.choice(PLANT_IDS, size=k, replace=False, p=PLANT_W))


for m in mats:
    m["plants"] = plants_for(m["MTART"])
    m["home"] = m["plants"][0]

# assign MATNRs in creation order (internal number ranges per type, like SAP)
mats.sort(key=lambda r: r["ERSDA"])
for m in mats:
    counter[m["MTART"]] += 1
    m["MATNR"] = str(num_range[m["MTART"]] + counter[m["MTART"]])

# ---- duplicates --------------------------------------------------------------
ABBR = {"FILM": ["FLM"], "PLAIN": ["PLN", "PLAN"], "MET": ["METALLISED", "METALIZED", "METT"],
        "PRINTED": ["PRNTD", "PRINT"], "LAMINATE": ["LAMI", "LAM", "LAMINATED"], "CORRUGATED": ["CORR", "CORRUGATD"],
        "BEARING": ["BRG", "BEARINGS"], "POUCH": ["PCH", "POUCHES"], "CARTON": ["CRTN", "CARTN"],
        "ADHESIVE": ["ADH", "ADHSV"], "SOLVENT": ["SOLV"], "SLEEVE": ["SLV"], "STRETCH": ["STRCH"],
        "PALLET": ["PLT"], "SPARE": ["SPR"], "CONSUMABLE": ["CONS"], "MOTOR": ["MTR"], "SENSOR": ["SNSR"]}


def typo(word: str) -> str:
    if len(word) < 5 or any(c.isdigit() for c in word):
        return word
    i = int(rng.integers(1, len(word) - 2))
    op = rng.random()
    if op < 0.4:
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]  # swap
    if op < 0.7:
        return word[:i] + word[i + 1:]                       # drop
    return word[:i] + word[i] + word[i:]                      # double


def vary_desc(d: str):
    """Return (variant, is_nonstandard). Numbers are never altered - a real
    duplicate has the same spec, typed differently."""
    toks = d.split(" ")
    out = []
    for t in toks:
        r = rng.random()
        if t in ABBR and r < 0.5:
            out.append(ch(ABBR[t]))
        elif t.endswith("MIC") and t[:-3].replace(".", "").isdigit() and r < 0.5:
            out.append(t[:-3] + ch([" MIC", "MICRON", " MICRON", "U"]))
        elif t.endswith("MM") and t[:-2].isdigit() and r < 0.4:
            out.append(t[:-2] + " MM")
        elif r < 0.12:
            out.append(typo(t))
        else:
            out.append(t)
    if rng.random() < 0.25 and len(out) > 2:        # token reorder e.g. "BOPP FILM ..."
        out[0], out[1] = out[1], out[0]
    v = " ".join(out)
    nonstd = False
    r = rng.random()
    if r < 0.12:
        v = v.lower() if rng.random() < 0.5 else v.title(); nonstd = True
    elif r < 0.17:
        v = v.replace(" ", "  ", 1); nonstd = True
    return (v[:40] if nonstd else v[:40].rstrip()), nonstd


dups = []
legacy = [m for m in mats if m["ERSDA"] < WINDOW_START]
dup_src = rng.choice(len(legacy), size=int(len(legacy) * MAT_DUP_RATE), replace=False)
for idx in dup_src:
    o = legacy[idx]
    for _ in range(1 + (rng.random() < 0.15)):
        d_date = o["ERSDA"] + timedelta(days=int(rng.exponential(700)) + 20)
        if d_date >= SNAPSHOT_DATE:
            d_date = rdate(WINDOW_START, SNAPSHOT_DATE - timedelta(days=1))
        if d_date >= PROGRAM_START and rng.random() > PREVENTION_FACTOR:
            continue  # search-before-create stopped this duplicate
        dup = {k: v for k, v in o.items() if k not in ("plants",)}
        desc, nonstd = vary_desc(o["MAKTX"])
        other = [p for p in PLANT_IDS if p not in o["plants"]] or PLANT_IDS
        dup.update(MAKTX=desc, ERSDA=d_date, home=ch(other), dup_of=o["MATNR"], nonstd=nonstd)
        dup["plants"] = list(dict.fromkeys([dup["home"]] + ([ch(o["plants"])] if rng.random() < 0.2 else [])))
        if rng.random() < 0.3:
            dup["BRGEW"] = round(o["BRGEW"] * 1.02, 4); dup["NTGEW"] = round(o["NTGEW"] * 1.02, 4)
        if o["MFRPN"] and rng.random() < 0.4:
            dup["MFRPN"] = None
        dup["miss_ean"] = bool(o["EAN11"]) and rng.random() < 0.5
        dup["miss_prdha"] = bool(o["PRDHA"]) and rng.random() < 0.3
        if dup["miss_ean"]:
            dup["EAN11"] = None
        if dup["miss_prdha"]:
            dup["PRDHA"] = None
        dups.append(dup)

dups.sort(key=lambda r: r["ERSDA"])
for d in dups:
    counter[d["MTART"]] += 1
    d["MATNR"] = str(num_range[d["MTART"]] + counter[d["MTART"]])
    d["resolved"] = resolve_date(d["ERSDA"] if d["ERSDA"] >= WINDOW_START else
                                 rdate(d["ERSDA"], WINDOW_START - timedelta(days=1)), "Critical", dup=True)
    inj = d["ERSDA"]
    log("M10", d["MATNR"], d["home"], inj, d["resolved"])
    # defects created alongside the duplicate are logged too
    if d["nonstd"]:
        log("M05", d["MATNR"], d["home"], inj, d["resolved"])
    if d["miss_ean"]:
        log("M08", d["MATNR"], d["home"], inj, d["resolved"])
    if d["miss_prdha"]:
        log("M07", d["MATNR"], d["home"], inj, d["resolved"])

open_dups = [d for d in dups if d["resolved"] is None]
current = mats + open_dups
print(f"  distinct={len(mats):,} duplicates created={len(dups):,} still open={len(open_dups):,}")

# ---- plant, valuation, description tables -------------------------------------
print("Building MARC / MBEW / MAKT ...")
for m in current:
    m.setdefault("dup_of", None)
    m["ERNAM"] = f"MDM_{m['home']}_{rng.integers(1, 5):02d}"
    m["LVORM"] = None
    m["MSTAE"] = None
    m["BISMT"] = f"OLD-{rng.integers(100000, 999999)}" if m["ERSDA"] < date(2012, 1, 1) and rng.random() < .6 else None
    r = rng.random()
    if r < 0.03:
        m["legit_state"] = "deleted"      # LVORM set, stock must be zero
    elif r < 0.09:
        m["legit_state"] = "obsolete"     # MSTAE=OB everywhere
    else:
        m["legit_state"] = "active"

marc, mbew, makt, usage = [], [], [], []
TARGET_STOCK_INR = 650e7   # ~Rs 650 Cr inventory for a ~Rs 5,000 Cr converter
for m in current:
    mt, g = m["MTART"], m["MATKL"]
    if m["price_range"]:
        base_price = float(rng.uniform(*m["price_range"]))
    else:
        base_price = float(np.clip(rng.lognormal(np.log(5000), 1.1), 150, 400000))
    for w in m["plants"]:
        pl = PLANTS[w]
        if mt in ("FERT", "HALB"):
            dismm = "PD" if rng.random() < .85 else "ND"; beskz = "E" if mt == "HALB" or rng.random() < .8 else "X"
        elif mt == "ERSA":
            dismm = "VB" if rng.random() < .6 else "ND"; beskz = "F"
        else:
            dismm = ch(["VB", "VB", "PD", "PD", "PD", "ND"]) if mt == "ROH" else ch(["VB", "PD", "ND"]); beskz = "F"
        price = round(base_price * float(rng.uniform(0.95, 1.05)), 2)
        vprsv = "S" if mt in ("FERT", "HALB") else "V"
        stock_val = 0.0 if (m["legit_state"] == "deleted" or rng.random() < 0.30) else float(rng.lognormal(10, 1.6))
        row = dict(MATNR=m["MATNR"], WERKS=w, DISMM=dismm, DISPO=f"{w[-2:]}{rng.integers(1, 6)}" if dismm != "ND" else None,
                   BESKZ=beskz, EKGRP=f"{w[:2]}{rng.integers(1, 9)}" if beskz in ("F", "X") else None,
                   PLIFZ=int(rng.integers(3, 91)) if beskz in ("F", "X") else 0,
                   MINBE=0.0, EISBE=0.0, MMSTA="OB" if m["legit_state"] == "obsolete" else None,
                   PRCTR=f"PC{w}{g[:2]}", STAWN=None, HERKL=None, LVORM=None)
        if pl["cross_border"] or rng.random() < 0.5:
            row["STAWN"] = m["STAWN"]; row["HERKL"] = ch(["IN", "IN", "IN", "CN", "TH", "DE", "US", "KR"])
        marc.append(row)
        mbew.append(dict(MATNR=m["MATNR"], BWKEY=w, VPRSV=vprsv, PEINH=1,
                         STPRS=price if vprsv == "S" else 0.0, VERPR=price if vprsv == "V" else round(price * 1.01, 2),
                         _stock_val=stock_val, _price=price))
    makt.append(dict(MATNR=m["MATNR"], SPRAS="E", MAKTX=m["MAKTX"]))
    for w in m["plants"]:
        if w in LOCAL_LANG:
            makt.append(dict(MATNR=m["MATNR"], SPRAS=LOCAL_LANG[w], MAKTX=m["MAKTX"]))

mbew_df = pd.DataFrame(mbew)
scale = TARGET_STOCK_INR / mbew_df["_stock_val"].sum()
mbew_df["_stock_val"] *= scale
mbew_df["LBKUM"] = (mbew_df["_stock_val"] / mbew_df["_price"]).round(3)
mbew_df["SALK3"] = (mbew_df["LBKUM"] * mbew_df["_price"]).round(2)
marc_df = pd.DataFrame(marc)
makt_df = pd.DataFrame(makt).drop_duplicates(["MATNR", "SPRAS"])

# MRP parameters consistent with stock
marc_df = marc_df.merge(mbew_df[["MATNR", "BWKEY", "LBKUM"]], left_on=["MATNR", "WERKS"], right_on=["MATNR", "BWKEY"]).drop(columns="BWKEY")
typical = np.where(marc_df["LBKUM"] > 0, marc_df["LBKUM"], rng.lognormal(5, 1, len(marc_df)))
marc_df["EISBE"] = np.where(marc_df["DISMM"] != "ND", (typical * rng.uniform(.1, .4, len(marc_df))).round(0) + 1, 0.0)
marc_df["MINBE"] = np.where(marc_df["DISMM"] == "VB", (marc_df["EISBE"] * 1.5).round(0) + 1, 0.0)
marc_df = marc_df.drop(columns="LBKUM")

# 12-month consumption (stands in for MSEG movement history)
turns = rng.lognormal(np.log(6), 0.6, len(mbew_df))
moving = rng.random(len(mbew_df)) < np.where(mbew_df["LBKUM"] > 0, 0.85, 0.5)
cons_val = np.where(mbew_df["LBKUM"] > 0, mbew_df["SALK3"] * turns, rng.lognormal(11, 1.5, len(mbew_df)))
usage_df = pd.DataFrame(dict(MATNR=mbew_df["MATNR"], WERKS=mbew_df["BWKEY"],
                             CONS_12M_VALUE=np.where(moving, cons_val, 0.0).round(0)))
usage_df["CONS_12M_QTY"] = (usage_df["CONS_12M_VALUE"] / mbew_df["_price"]).round(2)

mara_df = pd.DataFrame([{k: m[k] for k in ["MATNR", "MTART", "MATKL", "MEINS", "BRGEW", "NTGEW", "GEWEI",
                                           "ERSDA", "ERNAM", "LVORM", "MSTAE", "PRDHA", "EAN11", "MFRPN", "MFRNR", "BISMT"]}
                       for m in current])
mara_df["VOLUM"] = None
mara_df.loc[mara_df["MATNR"].isin([m["MATNR"] for m in current if m["legit_state"] == "deleted"]), "LVORM"] = "X"
mara_df.loc[mara_df["MATNR"].isin([m["MATNR"] for m in current if m["legit_state"] == "obsolete"]), "MSTAE"] = "OB"
meta = pd.DataFrame([dict(MATNR=m["MATNR"], home=m["home"], ERSDA=m["ERSDA"]) for m in current]).set_index("MATNR")

# =============================================================================
# 2. Inject rule-level defects into the material side
# =============================================================================
print("Injecting material/plant defects ...")
assert mara_df.MATNR.is_unique, "dup MATNR"
taken = defaultdict(set)   # rule -> keys already defected (keeps rules independent & detectable)


def inject(rule_id, cand: pd.DataFrame, keys: pd.Series, plants: pd.Series, created: pd.Series,
           apply_fn, exclude=()):
    """Vectorised draw of which applicable records get the defect, then a
    per-defect lifecycle (inject -> maybe resolved). Only still-open defects
    are written into the data, exactly like a real system today."""
    sev = RULE[rule_id]["severity"]; p = RULE[rule_id]["p_backlog"]
    # never re-inject a rule on a record that already carries it (e.g. a duplicate's creation defects)
    ex = set(taken[rule_id]).union(*[taken[e] for e in exclude])
    keep = ~keys.isin(ex).values
    cand, keys, plants = cand[keep], keys[keep], plants[keep]
    cr = pd.to_datetime(created[keep])
    backlog = (cr < pd.Timestamp(WINDOW_START)).values
    post = (cr >= pd.Timestamp(PROGRAM_START)).values
    prob = p * np.where(post, PREVENTION_FACTOR, 1.0)
    hits = np.flatnonzero(rng.random(len(cand)) < prob)
    for i in hits:
        c = cr.iloc[i].date()
        inj = rdate(c, WINDOW_START - timedelta(days=1)) if backlog[i] else c
        res = resolve_date(inj, sev)
        key = keys.iloc[i]
        log(rule_id, key, plants.iloc[i], inj, res)
        taken[rule_id].add(key)
        if res is None:
            apply_fn(cand.index[i], cand.iloc[i])
    return len(hits)


mara_df = mara_df.set_index("MATNR", drop=False)
def M(df):   # material-level keys, owning plant, creation date
    return df["MATNR"], df["MATNR"].map(meta["home"]), df["MATNR"].map(meta["ERSDA"])


def P(df):   # plant-level keys
    return df["MATNR"] + "|" + df["WERKS"], df["WERKS"], df["MATNR"].map(meta["ERSDA"])
dup_keys = {d["MATNR"] for d in open_dups}

# dups already carry their own M05/M07/M08 from creation - exclude them from re-injection
taken["M05"] |= {d["MATNR"] for d in dups if d["nonstd"]}
taken["M07"] |= {d["MATNR"] for d in dups if d["miss_prdha"]}
taken["M08"] |= {d["MATNR"] for d in dups if d["miss_ean"]}


def set_mara(col, val):
    def f(idx, row):
        mara_df.at[idx, col] = val(row) if callable(val) else val
    return f


inject("M01", mara_df, *M(mara_df), set_mara("MATKL", None))
inject("M04", mara_df, *M(mara_df),
       set_mara("MEINS", lambda r: ch([u for u in ALL_UOM if u not in ALLOWED_UOM[r["MATKL"]]])), exclude=["M01"])
inject("M02", mara_df, *M(mara_df), set_mara("NTGEW", lambda r: round(r["BRGEW"] * float(rng.uniform(1.1, 3)), 4)))
inject("M03", mara_df, *M(mara_df), set_mara("GEWEI", None))
fert = mara_df[mara_df["MTART"] == "FERT"]
inject("M07", fert, *M(fert), set_mara("PRDHA", None))
fe = fert[fert["EAN11"].notna()]
inject("M08", fe, *M(fe),
       set_mara("EAN11", lambda r: None if rng.random() < .5 else r["EAN11"][:12] + str((int(r["EAN11"][12]) + 3) % 10)))

# M09 deletion flag with stock
stock_by_mat = mbew_df.groupby("MATNR")["LBKUM"].sum()
has_stock = mara_df[(mara_df["MATNR"].map(stock_by_mat) > 0) & mara_df["LVORM"].isna()]
inject("M09", has_stock, *M(has_stock), set_mara("LVORM", "X"))

# MAKT rules
makt_df = makt_df.set_index(["MATNR", "SPRAS"], drop=False)
makt_e = mara_df[["MATNR"]]
drop_e = []


def m06(idx, row):
    drop_e.append(row["MATNR"])


def m05(idx, row):
    t = makt_df.at[(row["MATNR"], "E"), "MAKTX"]
    r = rng.random()
    if r < .35:
        t = t.lower()
    elif r < .55:
        t = t[:39] + " "          # trailing blank (MAKTX is CHAR 40)
    elif r < .75:
        t = t.replace(" ", "  ", 1)[:40]
    else:
        t = (ch(["TEST ", "DO NOT USE ", "DUMMY "]) + t)[:40]
    makt_df.at[(row["MATNR"], "E"), "MAKTX"] = t


inject("M06", makt_e, *M(makt_e), m06, exclude=["M05"])
inject("M05", makt_e, *M(makt_e), m05, exclude=["M06"])
makt_df = makt_df[~((makt_df["SPRAS"] == "E") & makt_df["MATNR"].isin(drop_e))].reset_index(drop=True)

# ---- plant-level rules (MARC / MBEW) -------------------------------------------
marc_df = marc_df.set_index(["MATNR", "WERKS"], drop=False)
assert marc_df.index.is_unique
mbew_df = mbew_df.set_index(["MATNR", "BWKEY"], drop=False)
mtart_of = mara_df["MTART"]


def set_marc(col, val):
    def f(idx, row):
        marc_df.at[idx, col] = val(row) if callable(val) else val
    return f


bought = marc_df[marc_df["MATNR"].map(mtart_of).isin(["ROH", "VERP", "HIBE", "ERSA"])]
inject("P01", bought, *P(bought), set_marc("BESKZ", "E"))
ext = marc_df[marc_df["BESKZ"].isin(["F", "X"])]
inject("P03", ext, *P(ext), set_marc("PLIFZ", lambda r: ch([0, 0, 240, 365, 999])), exclude=["P01"])
vb = marc_df[marc_df["DISMM"] == "VB"]
inject("P02", vb, *P(vb), set_marc("MINBE", 0.0))
pdvb = marc_df[marc_df["DISMM"].isin(["PD", "VB"])]
inject("P04", pdvb, *P(pdvb), set_marc("DISPO", None))
xb = [w for w, p in PLANTS.items() if p["cross_border"]]
p05c = marc_df[marc_df["WERKS"].isin(xb) & marc_df["MATNR"].map(mtart_of).isin(["ROH", "FERT"])]


def p05(idx, row):
    r = rng.random()
    if r < .6:
        marc_df.at[idx, "STAWN"] = None
    elif r < .85:
        marc_df.at[idx, "HERKL"] = None
    else:
        marc_df.at[idx, "STAWN"] = None; marc_df.at[idx, "HERKL"] = None


inject("P05", p05c, *P(p05c), p05)
obs = marc_df[marc_df["MATNR"].map(mara_df["MSTAE"]).isin(["OB", "BL"])]
inject("P08", obs, *P(obs), set_marc("MMSTA", None))

# valuation rules
mbew_df = mbew_df.rename(columns={"BWKEY": "WERKS"})
mbew_df.index.names = ["MATNR", "WERKS"]
s_stock = mbew_df[(mbew_df["VPRSV"] == "S") & (mbew_df["LBKUM"] > 0)]


def p06(idx, row):
    mbew_df.at[idx, "STPRS"] = 0.0
    mbew_df.at[idx, "SALK3"] = 0.0


inject("P06", s_stock, *P(s_stock), p06)
# P07: outlier vs (material group, plant) median - only where groups are big enough
mb = mbew_df.copy()
mb["MATKL"] = mb["MATNR"].map(mara_df["MATKL"]); mb["MTART"] = mb["MATNR"].map(mara_df["MTART"])
mb["price"] = np.where(mb["VPRSV"] == "S", mb["STPRS"], mb["VERPR"])
elig = mb[mb["MTART"].isin(["ROH", "HALB", "FERT", "VERP"]) & mb["MATKL"].notna() & (mb["price"] > 0)]
_g = [elig["MATKL"].values, elig["WERKS"].values]
gsize = elig.groupby(_g)["price"].transform("size")
gmed = elig.groupby(_g)["price"].transform("median")
elig = elig.assign(gmed=gmed)[gsize >= 30]
# large price errors get corrected at month-end; small ones remain
elig = elig[elig["LBKUM"] * elig["price"] < (elig["LBKUM"] * elig["price"]).quantile(0.7)]


def p07(idx, row):
    f = float(rng.uniform(12, 20)) if rng.random() < .6 else float(rng.uniform(.03, .08))
    newp = round(row["gmed"] * f, 2)
    col = "STPRS" if row["VPRSV"] == "S" else "VERPR"
    mbew_df.at[idx, col] = newp
    mbew_df.at[idx, "SALK3"] = round(newp * row["LBKUM"], 2)


inject("P07", elig, *P(elig), p07, exclude=["P06"])

# =============================================================================
# 3. Vendor master
# =============================================================================
print("Generating vendors ...")
IN_CITIES = [  # city, state(REGIO), GST state code, PIN prefix, alias
    ("Mumbai", "MH", "27", "400", "Bombay"), ("Pune", "MH", "27", "411", "Poona"), ("Nashik", "MH", "27", "422", None),
    ("Aurangabad", "MH", "27", "431", "Sambhajinagar"), ("Ahmedabad", "GJ", "24", "380", "Amdavad"),
    ("Vadodara", "GJ", "24", "390", "Baroda"), ("Vapi", "GJ", "24", "396", None), ("Silvassa", "DH", "26", "396", None),
    ("Chennai", "TN", "33", "600", "Madras"), ("Coimbatore", "TN", "33", "641", "Kovai"),
    ("Bengaluru", "KA", "29", "560", "Bangalore"), ("New Delhi", "DL", "07", "110", "Delhi"),
    ("Gurugram", "HR", "06", "122", "Gurgaon"), ("Faridabad", "HR", "06", "121", None), ("Noida", "UP", "09", "201", None),
    ("Hyderabad", "TS", "36", "500", "Secunderabad"), ("Kolkata", "WB", "19", "700", "Calcutta"), ("Baddi", "HP", "02", "173", None),
]
FOREIGN = {  # country: (cities, postcode fn, legal forms, name parts)
    "TH": (["Bangkok", "Rayong", "Chonburi"], lambda: f"{rng.integers(10000, 99999)}", ["Co., Ltd.", "Public Co., Ltd."],
           ["Siam", "Thai", "Eastern", "Chao Phraya", "Rayong", "Sukhumvit", "Bangna", "Laem Chabang", "Krungthep",
            "Chaiyo", "Mekong", "Lanna", "Srinakarin", "Ratchada"]),
    "PL": (["Poznan", "Warszawa", "Wroclaw"], lambda: f"{rng.integers(10, 99)}-{rng.integers(100, 999)}", ["Sp. z o.o.", "S.A."],
           ["Poz", "Pol", "Bal", "Wielko", "Warta", "Mazo", "Silesia", "Odra", "Wis", "Kra", "Lech", "Gniezno", "Tor", "Opal"]),
    "DE": (["Neuss", "Duesseldorf", "Koeln", "Hamburg"], lambda: f"{rng.integers(10000, 99999)}", ["GmbH", "GmbH & Co. KG", "AG"],
           ["Rhein", "Nord", "Sued", "Westfalen", "Hanse", "Ruhr", "Mosel", "Elbe", "Weser", "Eifel", "Taunus", "Harz", "Saar", "Lippe"]),
    "US": (["Columbus", "Chicago", "Houston", "Atlanta"], lambda: f"{rng.integers(10000, 99999)}", ["Inc.", "LLC", "Corp."],
           ["Great Lakes", "Buckeye", "Midwest", "Liberty", "Keystone", "Pioneer", "Summit", "Heartland", "Ridge", "Prairie",
            "Frontier", "Lakeshore", "Patriot", "Allegheny"]),
    "MX": (["Queretaro", "Monterrey", "Ciudad de Mexico"], lambda: f"{rng.integers(10000, 99999)}", ["S.A. de C.V.", "S. de R.L. de C.V."],
           ["Bajio", "Azteca", "Sierra", "Norte", "Queretana", "Pacifico", "Anahuac", "Real", "Maya", "Plata", "Condor",
            "Laguna", "Centauro", "Olmeca"]),
}
IN_PREFIX = ["Shree", "Shri", "Sai", "Om", "Jai", "Balaji", "Ganesh", "Laxmi", "Krishna", "Vinayak", "Siddhi", "Mahalaxmi",
             "Ambika", "Bharat", "Hindustan", "National", "Supreme", "Royal", "Classic", "Perfect", "Precision", "Apex",
             "Unique", "Global", "Allied", "United", "Western", "Eastern", "Deccan", "Sahyadri", "Konkan", "Narmada",
             "Kaveri", "Tirupati", "Sunrise", "Galaxy", "Everest", "Pioneer", "Vardhman", "Parth", "Aditya", "Surya"]
IN_MID = ["", "", "", "Patel", "Shah", "Mehta", "Agarwal", "Jain", "Kulkarni", "Deshmukh", "Iyer", "Reddy", "Rao",
          "Joshi", "Gupta", "Bansal", "Chawla", "Sethi", "Nair", "Pillai"]
IN_IND = ["Polymers", "Plastics", "Flexi Pack", "Packaging", "Chemicals", "Inks", "Engineering", "Enterprises", "Industries",
          "Traders", "Corrugators", "Paper Mills", "Laminates", "Films", "Resins", "Logistics", "Tools", "Electricals",
          "Automation", "Bearings", "Hydraulics", "Fabricators", "Adhesives", "Rubber Products"]
IN_LEGAL = ["Pvt Ltd", "Pvt Ltd", "Private Limited", "LLP", "Ltd", ""]
IND_EN = ["Packaging", "Chemical", "Polymer", "Engineering", "Industrial Supply", "Logistics", "Films", "Automation"]
IND_LOCAL = {"PL": ["Pak", "Chem", "Plast", "Tech", "Trans"], "DE": ["Verpackung", "Chemie", "Kunststoff", "Maschinenbau", "Logistik"],
             "MX": ["Empaques", "Plasticos", "Quimicos", "Industrial", "Logistica"]}


def pan(entity="C"):
    L = string.ascii_uppercase
    return "".join(rng.choice(list(L), 3)) + entity + ch(L) + f"{rng.integers(1000, 9999)}" + ch(L)


def phone(country):
    if country == "IN":
        return f"+91 {rng.integers(70000, 99999)} {rng.integers(10000, 99999)}"
    cc = {"TH": "66", "PL": "48", "DE": "49", "US": "1", "MX": "52"}[country]
    return f"+{cc} {rng.integers(100, 999)} {rng.integers(100, 999)} {rng.integers(1000, 9999)}"


countries = rng.choice(["IN", "TH", "PL", "DE", "US", "MX"], size=N_VENDORS, p=[.70, .08, .06, .06, .05, .05])
vendors, seen_names, seen_keys = [], set(), set()
for i, c in enumerate(countries):
    for _ in range(30):
        if c == "IN":
            city = IN_CITIES[int(rng.integers(len(IN_CITIES)))]
            legal = ch(IN_LEGAL)
            name = " ".join(x for x in [ch(IN_PREFIX), ch(IN_MID), ch(IN_IND), legal] if x)
        else:
            cities, pc, legals, parts = FOREIGN[c]
            ind = ch(IND_LOCAL.get(c, IND_EN))
            p1, p2 = rng.choice(parts, 2, replace=False)
            name = f"{p1}{ind.lower() if c == 'PL' else ' ' + p2 + ' ' + ind} {ch(legals)}" if c != "PL" else \
                   f"{p1}{ind.lower()} {p2} {ch(legals)}"
        key = (std_vendor_name(name), city[0] if c == "IN" else None)
        if name.upper() not in seen_names and key not in seen_keys:
            break
    if len(name) > 35:
        name = name.replace("Private Limited", "Pvt Ltd")
    name = name[:35].rstrip()
    seen_names.add(name.upper()); seen_keys.add(key)
    v = dict(entity_id=f"VEN-E{i:06d}", NAME1=name[:35], LAND1=c, ERDAT=creation_date())
    if c == "IN":
        v.update(ORT01=city[0], REGIO=city[1], PSTLZ=f"{city[3]}{rng.integers(0, 999):03d}", city_alias=city[4])
        entity = "F" if "LLP" in name or legal == "" else "C"
        g14 = f"{city[2]}{pan(entity)}1Z"
        v["STCD3"] = g14 + gst_checksum(g14)
        v["STCEG"] = None
    else:
        cities, pc, _, _ = FOREIGN[c]
        v.update(ORT01=ch(cities), REGIO=None, PSTLZ=pc(), city_alias=None, STCD3=None,
                 STCEG=f"{c}{rng.integers(10**8, 10**9 - 1)}" if c in ("PL", "DE") else None)
    v["STRAS"] = f"{rng.integers(1, 400)}, {ch(['MIDC','GIDC','Industrial Area','Phase II','Sector 7','Plot','Estate','Road','Park'])} {ch(['Road','Lane','Nagar','Street','Avenue','Zone'])}"
    v["TELF1"] = phone(c) if rng.random() < .9 else None
    dom = "".join(ch_ for ch_ in name.lower().split(" ")[0] if ch_.isalpha())[:12] or "vendor"
    v["SMTP_ADDR"] = f"{ch(['sales','accounts','info','orders'])}@{dom}{rng.integers(1, 99)}.{ 'in' if c == 'IN' else 'com'}" if (v["TELF1"] is None or rng.random() < .8) else None
    if v["TELF1"] is None and v["SMTP_ADDR"] is None:
        v["TELF1"] = phone(c)
    v["KTOKK"] = "ZDOM" if c == "IN" else "ZIMP"
    home_bukrs = {"IN": "1000", "TH": "2000", "PL": "3000", "DE": "3100", "US": "4000", "MX": "5000"}[c]
    others = [b for b in COMPANY_CODES if b != home_bukrs]
    v["bukrs"] = [home_bukrs] + list(rng.choice(others, size=int(rng.choice([0, 0, 0, 1, 1, 2])), replace=False))
    v["home"] = home_bukrs
    # bank
    if rng.random() < .92:
        if c == "IN":
            v["BANKL"] = f"{ch(['HDFC','ICIC','SBIN','UTIB','KKBK','YESB','IDFB'])}0{rng.integers(100000, 999999)}"
        else:
            v["BANKL"] = f"{''.join(rng.choice(list(string.ascii_uppercase), 4))}{c}{''.join(rng.choice(list(string.ascii_uppercase + string.digits), 2))}"
        v["BANKN"] = str(rng.integers(10**10, 10**14))
    else:
        v["BANKL"] = v["BANKN"] = None
    vendors.append(v)

vendors.sort(key=lambda r: r["ERDAT"])
for k, v in enumerate(vendors):
    v["LIFNR"] = f"{200000 + k:010d}"

# ---- vendor duplicates ------------------------------------------------------------
LEGAL_VARIANTS = {"Pvt Ltd": ["Private Limited", "Pvt. Ltd.", "P. Ltd.", "Pvt Limited", "PVT LTD"],
                  "Private Limited": ["Pvt Ltd", "Pvt. Ltd", "Pvt. Limited"], "Ltd": ["Limited", "Ltd."],
                  "LLP": ["L.L.P."], "Co., Ltd.": ["Company Limited", "Co Ltd"], "GmbH": ["G.m.b.H."],
                  "Inc.": ["Incorporated", "Inc"], "LLC": ["L.L.C."], "Sp. z o.o.": ["Sp.z o.o.", "Spolka z o.o."],
                  "S.A. de C.V.": ["SA de CV", "S.A. DE C.V."]}
NAME_VARIANTS = {"Shree": ["Shri", "Sree", "Sri"], "Shri": ["Shree", "Sri"], "Enterprises": ["Enterprise", "Entp."],
                 "Industries": ["Industry", "Inds."], "Polymers": ["Polymer"], "Plastics": ["Plastic"],
                 "Engineering": ["Engg.", "Engg"], "Chemicals": ["Chemical", "Chem"], "Packaging": ["Packagings", "Pkg"],
                 "Laminates": ["Laminate"], "Traders": ["Trading Co", "Trader"], "Electricals": ["Electrical"]}


def vary_name(n: str) -> str:
    out = n
    for base, alts in LEGAL_VARIANTS.items():
        if out.endswith(base) and rng.random() < .7:
            out = out[: -len(base)] + ch(alts); break
    toks = out.split(" ")
    toks = [ch(NAME_VARIANTS[t]) if t in NAME_VARIANTS and rng.random() < .5 else (typo(t) if rng.random() < .08 else t) for t in toks]
    out = " ".join(toks)
    r = rng.random()
    if r < .2:
        out = out.upper()
    elif r < .3:
        out = "M/s " + out
    return out[:35].rstrip()


vdups = []
leg_v = [v for v in vendors if v["ERDAT"] < WINDOW_START]
for idx in rng.choice(len(leg_v), size=int(len(leg_v) * VEN_DUP_RATE), replace=False):
    o = leg_v[idx]
    d_date = o["ERDAT"] + timedelta(days=int(rng.exponential(600)) + 15)
    if d_date >= SNAPSHOT_DATE:
        d_date = rdate(WINDOW_START, SNAPSHOT_DATE - timedelta(days=1))
    if d_date >= PROGRAM_START and rng.random() > PREVENTION_FACTOR:
        continue
    d = {k: v for k, v in o.items()}
    d.update(NAME1=vary_name(o["NAME1"]), ERDAT=d_date, dup_of=o["LIFNR"])
    other_bukrs = o["bukrs"][1:] or [o["home"]]
    d["home"] = ch(other_bukrs) if rng.random() < .5 else o["home"]
    d["bukrs"] = [d["home"]]
    d["flags"] = []
    if o["city_alias"] and rng.random() < .5:
        d["ORT01"] = o["city_alias"]
    r = rng.random()
    if r < .15 and o["PSTLZ"]:
        p = list(o["PSTLZ"]); j = len(p) - 1 - int(rng.integers(0, 2))
        if p[j].isdigit():
            p[j] = str((int(p[j]) + 1) % 10)
        d["PSTLZ"] = "".join(p)
    elif r < .27:
        d["PSTLZ"] = None; d["flags"].append("V03")
    if o["LAND1"] == "IN" and rng.random() < .35:
        d["STCD3"] = None; d["flags"].append("V01")
    if rng.random() < .3:
        d["TELF1"] = None
    elif d["TELF1"]:
        d["TELF1"] = d["TELF1"].replace(" ", "").replace("+91", "0") if rng.random() < .5 else d["TELF1"]
    if rng.random() < .3:
        d["SMTP_ADDR"] = None
    elif d["SMTP_ADDR"] and rng.random() < .3:
        d["SMTP_ADDR"] = d["SMTP_ADDR"].upper()
    if d["TELF1"] is None and d["SMTP_ADDR"] is None:
        d["flags"].append("V06")
    if rng.random() < .3 or not o["BANKN"]:
        d["BANKL"] = d["BANKN"] = None   # new record created without bank; or different
    if rng.random() < .15:
        d["STRAS"] = d["STRAS"].replace("Road", "Rd").replace("Industrial", "Indl")
    vdups.append(d)

vdups.sort(key=lambda r: r["ERDAT"])
for k, d in enumerate(vdups):
    d["LIFNR"] = f"{200000 + len(vendors) + k:010d}"
    d["resolved"] = resolve_date(d["ERDAT"] if d["ERDAT"] >= WINDOW_START else
                                 rdate(d["ERDAT"], WINDOW_START - timedelta(days=1)), "Critical", dup=True)
    log("V07", d["LIFNR"], d["home"], d["ERDAT"], d["resolved"])
    for f in d["flags"]:
        log(f, d["LIFNR"], d["home"], d["ERDAT"], d["resolved"])
    if d["TELF1"] is None and d["SMTP_ADDR"] is None and "V06" not in d["flags"]:
        pass

open_vdups = [d for d in vdups if d["resolved"] is None]
vcur = vendors + open_vdups
for v in vcur:
    v.setdefault("dup_of", None)
    v["ERNAM"] = f"AP_{v['home']}_{rng.integers(1, 4):02d}"
    v["SPERR"] = None
    v["LOEVM"] = None
print(f"  distinct={len(vendors):,} duplicates created={len(vdups):,} still open={len(open_vdups):,}")

lfa1_df = pd.DataFrame([{k: v[k] for k in ["LIFNR", "NAME1", "STRAS", "ORT01", "PSTLZ", "REGIO", "LAND1", "TELF1",
                                           "SMTP_ADDR", "STCD3", "STCEG", "KTOKK", "SPERR", "LOEVM", "ERDAT", "ERNAM"]}
                       for v in vcur]).set_index("LIFNR", drop=False)
lfb1_rows, lfbk_rows, spend_rows = [], [], []
for v in vcur:
    for b in v["bukrs"]:
        lfb1_rows.append(dict(LIFNR=v["LIFNR"], BUKRS=b, AKONT="160000", ZTERM=ch(["Z030", "Z045", "Z060", "Z090"]),
                              ZWELS="T"))
        active = rng.random() < .8
        spend_rows.append(dict(LIFNR=v["LIFNR"], BUKRS=b, SPEND_12M_INR=float(rng.lognormal(np.log(15e5), 1.8)) if active else 0.0))
    if v["BANKN"]:
        lfbk_rows.append(dict(LIFNR=v["LIFNR"], BANKS=v["LAND1"], BANKL=v["BANKL"], BANKN=v["BANKN"],
                              KOINH=v["NAME1"][:35]))
lfb1_df = pd.DataFrame(lfb1_rows).set_index(["LIFNR", "BUKRS"], drop=False)
lfbk_df = pd.DataFrame(lfbk_rows).set_index("LIFNR", drop=False)
spend_df = pd.DataFrame(spend_rows)
spend_df["SPEND_12M_INR"] *= 3200e7 / spend_df["SPEND_12M_INR"].sum()   # ~Rs 3,200 Cr addressable spend
spend_df["SPEND_12M_INR"] = spend_df["SPEND_12M_INR"].round(0)
# legit posting blocks only on vendors with no spend
vspend = spend_df.groupby("LIFNR")["SPEND_12M_INR"].sum()
zero_spend = vspend[vspend == 0].index
lfa1_df.loc[lfa1_df.index.isin(rng.choice(zero_spend, size=len(zero_spend) // 5, replace=False)), "SPERR"] = "X"

# ---- vendor rule defects ----------------------------------------------------------
print("Injecting vendor defects ...")
vmeta = {v["LIFNR"]: v for v in vcur}
taken["V01"] |= {d["LIFNR"] for d in vdups if "V01" in d["flags"]}
taken["V03"] |= {d["LIFNR"] for d in vdups if "V03" in d["flags"]}
taken["V06"] |= {d["LIFNR"] for d in vdups if "V06" in d["flags"]}
vhome = pd.Series({k: v["home"] for k, v in vmeta.items()})
vdate = pd.Series({k: v["ERDAT"] for k, v in vmeta.items()})


def V(df):
    return df["LIFNR"], df["LIFNR"].map(vhome), df["LIFNR"].map(vdate)


def set_lfa1(col, val):
    def f(idx, row):
        lfa1_df.at[idx, col] = val(row) if callable(val) else val
    return f


india = lfa1_df[lfa1_df["LAND1"] == "IN"]
inject("V01", india, *V(india), set_lfa1("STCD3", None))


def bad_gstin(r):
    g = r["STCD3"]; k = rng.random()
    if k < .4:   # typo in PAN part -> checksum fails
        j = int(rng.integers(2, 12)); c = g[j]
        rep = ch([x for x in (string.digits if c.isdigit() else string.ascii_uppercase) if x != c])
        g2 = g[:j] + rep + g[j + 1:]
        return g2 if gst_checksum(g2[:14]) != g2[14] else g2[:14] + ("0" if g2[14] != "0" else "1")
    if k < .7:   # state code of another state (vendor moved / copied from branch)
        sc = ch([s[2] for s in IN_CITIES if s[2] != g[:2]]); g14 = sc + g[2:14]
        return g14 + gst_checksum(g14)
    return g[:14]   # truncated


ig = india[india["STCD3"].notna()]
inject("V02", ig, *V(ig), set_lfa1("STCD3", bad_gstin), exclude=["V01"])


def bad_pc(r):
    if rng.random() < .4:
        return None
    return {"IN": lambda: f"{rng.integers(10000, 99999)}", "PL": lambda: f"{rng.integers(10000, 99999)}"}.get(
        r["LAND1"], lambda: f"{rng.integers(100, 9999)}")()


inject("V03", lfa1_df, *V(lfa1_df), set_lfa1("PSTLZ", bad_pc))


def v06(idx, row):
    lfa1_df.at[idx, "TELF1"] = None; lfa1_df.at[idx, "SMTP_ADDR"] = None


inject("V06", lfa1_df, *V(lfa1_df), v06)
spend_pos = vspend[vspend > 0].index
act = lfa1_df[lfa1_df.index.isin(spend_pos) & lfa1_df["SPERR"].isna()]
inject("V08", act, *V(act), set_lfa1("SPERR", "X"))
inject("V04", lfb1_df, lfb1_df["LIFNR"] + "|" + lfb1_df["BUKRS"], lfb1_df["BUKRS"], lfb1_df["LIFNR"].map(vdate),
       lambda idx, row: lfb1_df.at.__setitem__((idx, "ZTERM"), None))

# V05: bank account copied from an unrelated vendor
acct_count = lfbk_df.groupby(["BANKL", "BANKN"]).size()
unique_acct = lfbk_df[lfbk_df.set_index(["BANKL", "BANKN"]).index.map(acct_count) == 1]
entity = {v["LIFNR"]: (v["dup_of"] or v["LIFNR"]) for v in vcur}
entity_accts = defaultdict(set)
for _, r in lfbk_df.iterrows():
    entity_accts[entity[r["LIFNR"]]].add((r["BANKL"], r["BANKN"]))
p = RULE["V05"]["p_backlog"]
used = set()
for lif, r in unique_acct.sample(frac=1, random_state=SEED).iterrows():
    if lif in used:
        continue
    inj = defect_injected(vmeta[lif]["ERDAT"], p)
    if inj is None:
        continue
    victim = unique_acct.sample(1, random_state=int(rng.integers(1e9))).iloc[0]
    if victim["LIFNR"] in used or entity[victim["LIFNR"]] == entity[lif] or victim["LIFNR"] == lif:
        continue
    res = resolve_date(inj, "Critical")
    for key in (lif, victim["LIFNR"]):
        log("V05", key, vmeta[key]["home"], inj, res)
        used.add(key)
    if res is None:
        lfbk_df.at[lif, "BANKL"] = victim["BANKL"]; lfbk_df.at[lif, "BANKN"] = victim["BANKN"]

# =============================================================================
# 4. Write everything
# =============================================================================
print("Writing parquet ...")
mbew_out = mbew_df.reset_index(drop=True).rename(columns={"WERKS": "BWKEY"})[
    ["MATNR", "BWKEY", "VPRSV", "PEINH", "STPRS", "VERPR", "LBKUM", "SALK3"]]
tables = {
    "mara": mara_df.reset_index(drop=True),
    "marc": marc_df.reset_index(drop=True),
    "makt": makt_df.reset_index(drop=True),
    "mbew": mbew_out,
    "lfa1": lfa1_df.reset_index(drop=True),
    "lfb1": lfb1_df.reset_index(drop=True),
    "lfbk": lfbk_df.reset_index(drop=True),
    "usage_12m": usage_df,
    "vendor_spend_12m": spend_df,
}
for name, df in tables.items():
    df.to_parquet(RAW / f"{name}.parquet", index=False)

truth_m = pd.DataFrame([dict(MATNR=m["MATNR"], entity_id=m["entity_id"], dup_of=m["dup_of"]) for m in current])
truth_v = pd.DataFrame([dict(LIFNR=v["LIFNR"], entity_id=v["entity_id"], dup_of=v["dup_of"]) for v in vcur])
truth_m.to_parquet(RAW / "_truth_material_entities.parquet", index=False)
truth_v.to_parquet(RAW / "_truth_vendor_entities.parquet", index=False)

led = pd.DataFrame(ledger)
led["injected_date"] = pd.to_datetime(led["injected_date"])
led["resolved_date"] = pd.to_datetime(led["resolved_date"])
assert not led.duplicated(["rule_id", "record_key"]).any(), "ledger must hold one entry per rule x record"
led.to_parquet(RAW / "_defect_ledger.parquet", index=False)
pd.DataFrame(RULES, columns=RULE_COLS).to_csv(RAW / "_rule_catalog.csv", index=False)

master = sum(len(tables[t]) for t in ["mara", "marc", "makt", "mbew", "lfa1", "lfb1", "lfbk"])
print("\nRow counts:")
for n, df in tables.items():
    print(f"  {n:18s} {len(df):>9,}")
print(f"  {'MASTER DATA TOTAL':18s} {master:>9,}")
print(f"  defect ledger      {len(led):>9,}  (open today: {led['resolved_date'].isna().sum():,})")
