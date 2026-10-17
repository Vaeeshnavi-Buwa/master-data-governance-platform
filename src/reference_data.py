"""
Standardisation lists applied before matching: abbreviations, vendor name tokens,
legal forms and city aliases ("PLN" -> "PLAIN" etc.).
"""
import re

# material description abbreviations -> canonical word
MAT_SYNONYMS = {
    "FLM": "FILM", "PLN": "PLAIN", "PLAN": "PLAIN", "METALLISED": "MET", "METALIZED": "MET", "METT": "MET",
    "PRNTD": "PRINTED", "PRINT": "PRINTED", "LAMI": "LAMINATE", "LAM": "LAMINATE", "LAMINATED": "LAMINATE",
    "CORR": "CORRUGATED", "CORRUGATD": "CORRUGATED", "BRG": "BEARING", "BEARINGS": "BEARING",
    "PCH": "POUCH", "POUCHES": "POUCH", "CRTN": "CARTON", "CARTN": "CARTON", "ADH": "ADHESIVE",
    "ADHSV": "ADHESIVE", "SOLV": "SOLVENT", "SLV": "SLEEVE", "STRCH": "STRETCH", "PLT": "PALLET",
    "SPR": "SPARE", "CONS": "CONSUMABLE", "MTR": "MOTOR", "SNSR": "SENSOR", "MICRON": "MIC", "U": "MIC",
}

# vendor name tokens -> canonical
VEN_SYNONYMS = {
    "SHRI": "SHREE", "SREE": "SHREE", "SRI": "SHREE", "ENGG": "ENGINEERING", "INDS": "INDUSTRIES",
    "INDUSTRY": "INDUSTRIES", "ENTP": "ENTERPRISES", "ENTERPRISE": "ENTERPRISES", "CHEM": "CHEMICALS",
    "CHEMICAL": "CHEMICALS", "PKG": "PACKAGING", "PACKAGINGS": "PACKAGING", "POLYMER": "POLYMERS",
    "PLASTIC": "PLASTICS", "LAMINATE": "LAMINATES", "TRADER": "TRADERS", "ELECTRICAL": "ELECTRICALS", "TRADING": "TRADERS",
}
# legal-form tokens carry no identity information for matching -> removed
# (punctuation is stripped first, so "S.A. de C.V." -> S A DE C V; single letters are dropped too)
LEGAL_TOKENS = {"PVT", "PRIVATE", "LTD", "LIMITED", "LLP", "CO", "COMPANY", "INC", "INCORPORATED", "LLC", "CORP",
                "GMBH", "AG", "KG", "SP", "OO", "SPOLKA", "SA", "DE", "CV", "RL", "PUBLIC", "MS", "&"}

CITY_ALIASES = {"BOMBAY": "MUMBAI", "POONA": "PUNE", "SAMBHAJINAGAR": "AURANGABAD", "AMDAVAD": "AHMEDABAD",
                "BARODA": "VADODARA", "MADRAS": "CHENNAI", "KOVAI": "COIMBATORE", "BANGALORE": "BENGALURU",
                "DELHI": "NEW DELHI", "GURGAON": "GURUGRAM", "SECUNDERABAD": "HYDERABAD", "CALCUTTA": "KOLKATA"}

_num_unit = re.compile(r"(\d+(?:\.\d+)?)\s*(MICRON|MIC|U|MM|GSM|KW|RPM|LPI|BCM|G|L|IN|PCT)\b")


def std_material_desc(s: str | None) -> str:
    if not isinstance(s, str) or not s:
        return ""
    s = re.sub(r"\s+", " ", s.upper().strip())
    s = re.sub(r"\b(TEST|DO NOT USE|DUMMY|COPY)\b", " ", s)
    s = _num_unit.sub(lambda m: m.group(1) + ("MIC" if m.group(2) in ("MICRON", "U") else m.group(2)), s)
    toks = [MAT_SYNONYMS.get(t, t) for t in s.split()]
    return " ".join(toks)


def num_signature(s: str) -> str:
    """Sorted tokens that carry a number WITH its unit/context (20MIC, 1020MM, D40917).
    Keeping the unit matters: 980LPI/1200MM is not 1200LPI/980MM."""
    toks = [t for t in s.split() if any(c.isdigit() for c in t)]
    return " ".join(sorted(toks))


def std_vendor_name(s: str | None) -> str:
    if not isinstance(s, str) or not s:
        return ""
    s = s.upper()
    s = re.sub(r"^M/S\.?\s*", " ", s)
    s = re.sub(r"[.,()/&-]", " ", s)
    toks = [VEN_SYNONYMS.get(t, t) for t in s.split() if len(t) > 1 and t not in LEGAL_TOKENS]
    return " ".join(toks)


def std_city(s: str | None) -> str:
    if not isinstance(s, str) or not s:
        return ""
    s = s.upper().strip()
    return CITY_ALIASES.get(s, s)


def phone_digits(s: str | None) -> str | None:
    if not isinstance(s, str) or not s:
        return None
    d = re.sub(r"\D", "", s)
    return d[-10:] if len(d) >= 10 else None
