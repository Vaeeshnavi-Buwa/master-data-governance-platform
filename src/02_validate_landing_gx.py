"""
Great Expectations checks on the raw extract before it is loaded.

GX handles the per-table contract (keys, allowed codes, ranges, row counts).
A hard failure stops the pipeline. Cross-table business rules, scoring and
history live in dbt.

Each expectation is tagged hard (contract) or soft (warning threshold via `mostly`).
Output: gx/ Data Docs and data/reports/gx_summary.json
"""
import json
import os
import sys

os.environ["TZ"] = "UTC"   # GX data-docs renderer needs an IANA zone

import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd

from config import PLANTS, RAW, REPORTS, ROOT, COMPANY_CODES

UOM = ["EA", "KG", "M", "L", "M2", "PAK", "TH", "SET", "ROL"]          # T006 subset in use
LANGS = ["E", "D", "L", "2", "S"]

CONTRACTS = {
    "mara": [
        ("hard", gxe.ExpectColumnValuesToNotBeNull(column="MATNR")),
        ("hard", gxe.ExpectColumnValuesToBeUnique(column="MATNR")),
        ("hard", gxe.ExpectColumnValuesToMatchRegex(column="MATNR", regex=r"^\d{8}$")),
        ("hard", gxe.ExpectColumnValuesToBeInSet(column="MTART", value_set=["ROH", "HALB", "FERT", "ERSA", "HIBE", "VERP"])),
        ("hard", gxe.ExpectColumnValuesToNotBeNull(column="ERSDA")),
        ("hard", gxe.ExpectColumnValuesToBeInSet(column="MEINS", value_set=UOM)),
        ("hard", gxe.ExpectTableRowCountToBeBetween(min_value=30_000, max_value=80_000)),
        ("hard", gxe.ExpectColumnValuesToBeBetween(column="BRGEW", min_value=0, max_value=5_000)),
        ("soft", gxe.ExpectColumnValuesToNotBeNull(column="MATKL", mostly=0.97)),
    ],
    "marc": [
        ("hard", gxe.ExpectCompoundColumnsToBeUnique(column_list=["MATNR", "WERKS"])),
        ("hard", gxe.ExpectColumnValuesToBeInSet(column="WERKS", value_set=list(PLANTS))),
        ("hard", gxe.ExpectColumnValuesToBeInSet(column="DISMM", value_set=["PD", "VB", "ND"])),
        ("hard", gxe.ExpectColumnValuesToBeInSet(column="BESKZ", value_set=["E", "F", "X"])),
        ("soft", gxe.ExpectColumnValuesToNotBeNull(column="DISPO", mostly=0.95,
                                                    row_condition='DISMM!="ND"', condition_parser="pandas")),
    ],
    "makt": [
        ("hard", gxe.ExpectCompoundColumnsToBeUnique(column_list=["MATNR", "SPRAS"])),
        ("hard", gxe.ExpectColumnValuesToBeInSet(column="SPRAS", value_set=LANGS)),
        ("hard", gxe.ExpectColumnValueLengthsToBeBetween(column="MAKTX", min_value=1, max_value=40)),
    ],
    "mbew": [
        ("hard", gxe.ExpectCompoundColumnsToBeUnique(column_list=["MATNR", "BWKEY"])),
        ("hard", gxe.ExpectColumnValuesToBeInSet(column="VPRSV", value_set=["S", "V"])),
        ("hard", gxe.ExpectColumnValuesToBeBetween(column="LBKUM", min_value=0)),
        ("hard", gxe.ExpectColumnValuesToBeBetween(column="STPRS", min_value=0)),
        ("soft", gxe.ExpectColumnSumToBeBetween(column="SALK3", min_value=4e9, max_value=9e9)),   # Rs 400-900 Cr inventory
    ],
    "lfa1": [
        ("hard", gxe.ExpectColumnValuesToBeUnique(column="LIFNR")),
        ("hard", gxe.ExpectColumnValuesToNotBeNull(column="NAME1")),
        ("hard", gxe.ExpectColumnValuesToBeInSet(column="LAND1", value_set=list(set(COMPANY_CODES.values())))),
        ("hard", gxe.ExpectColumnValuesToBeInSet(column="KTOKK", value_set=["ZDOM", "ZIMP"])),
        ("soft", gxe.ExpectColumnValuesToMatchRegex(column="STCD3", regex=r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$", mostly=0.97)),
    ],
    "lfb1": [
        ("hard", gxe.ExpectCompoundColumnsToBeUnique(column_list=["LIFNR", "BUKRS"])),
        ("hard", gxe.ExpectColumnValuesToBeInSet(column="BUKRS", value_set=list(COMPANY_CODES))),
        ("soft", gxe.ExpectColumnValuesToNotBeNull(column="ZTERM", mostly=0.98)),
    ],
    "lfbk": [
        ("hard", gxe.ExpectColumnValuesToNotBeNull(column="LIFNR")),
        ("hard", gxe.ExpectColumnValuesToMatchRegex(column="BANKN", regex=r"^\d{6,18}$")),
    ],
}


def main() -> int:
    context = gx.get_context(mode="file", project_root_dir=str(ROOT))
    ds = context.data_sources.add_or_update_pandas("sap_landing")
    summary, hard_fail = [], False
    for table, exps in CONTRACTS.items():
        df = pd.read_parquet(RAW / f"{table}.parquet")
        try:
            asset = ds.get_asset(table)
        except Exception:
            asset = ds.add_dataframe_asset(name=table)
        try:
            bd = asset.get_batch_definition("full_extract")
        except Exception:
            bd = asset.add_batch_definition_whole_dataframe("full_extract")
        suite = gx.ExpectationSuite(name=f"{table}_contract")
        for sev, e in exps:
            e.meta = {"severity": sev}
            suite.add_expectation(e)
        suite = context.suites.add_or_update(suite)
        vd = context.validation_definitions.add_or_update(
            gx.ValidationDefinition(name=f"{table}_landing", data=bd, suite=suite))
        res = vd.run(batch_parameters={"dataframe": df})
        for r in res.results:
            sev = r.expectation_config.meta.get("severity", "hard")
            ok = bool(r.success)
            hard_fail |= (sev == "hard" and not ok)
            unexpected = r.result.get("unexpected_percent")
            summary.append(dict(table=table, expectation=r.expectation_config.type,
                                column=r.expectation_config.kwargs.get("column") or r.expectation_config.kwargs.get("column_list"),
                                severity=sev, success=ok,
                                unexpected_pct=round(unexpected, 3) if unexpected is not None else None,
                                observed=r.result.get("observed_value")))
        print(f"  {table:5s} rows={len(df):>8,}  expectations={len(exps)}  "
              f"failed={sum(1 for s in summary if s['table'] == table and not s['success'])}")
    context.build_data_docs()
    out = dict(pipeline_gate="FAIL" if hard_fail else "PASS", results=summary)
    (REPORTS / "gx_summary.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"GX landing gate: {out['pipeline_gate']}  (Data Docs: gx/uncommitted/data_docs/local_site/index.html)")
    for s in summary:
        if not s["success"]:
            print(f"   [{s['severity'].upper()}] {s['table']}.{s['column']} {s['expectation']} unexpected={s['unexpected_pct']}%")
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
