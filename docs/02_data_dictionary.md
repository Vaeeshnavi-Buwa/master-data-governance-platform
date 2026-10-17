# Data dictionary

## Source tables (synthetic SAP extract, `data/raw/`)

| Table | Rows | Key | Fields used |
|---|---|---|---|
| MARA | 50,567 | MATNR | MTART type, MATKL material group, MEINS base UoM, BRGEW/NTGEW/GEWEI weights, ERSDA created, ERNAM creator (`MDM_<plant>_nn`), LVORM deletion flag, MSTAE cross-plant status, PRDHA product hierarchy, EAN11, MFRPN/MFRNR manufacturer part, BISMT old material no. |
| MARC | 146,266 | MATNR+WERKS | DISMM MRP type, DISPO MRP controller, BESKZ procurement type, EKGRP purchasing group, PLIFZ planned delivery days, MINBE reorder point, EISBE safety stock, MMSTA plant status, PRCTR, STAWN HS code, HERKL country of origin |
| MAKT | 113,715 | MATNR+SPRAS | MAKTX description (CHAR 40) in E, D, L (Polish), 2 (Thai), S |
| MBEW | 146,266 | MATNR+BWKEY | VPRSV price control, STPRS standard price, VERPR moving price, LBKUM stock qty, SALK3 stock value (INR) |
| LFA1 | 12,299 | LIFNR | NAME1, STRAS, ORT01, PSTLZ, REGIO, LAND1, TELF1, SMTP_ADDR, STCD3 GSTIN, STCEG VAT, KTOKK, SPERR posting block, ERDAT, ERNAM (`AP_<bukrs>_nn`) |
| LFB1 | 20,024 | LIFNR+BUKRS | AKONT recon account, ZTERM payment terms, ZWELS payment methods |
| LFBK | 11,127 | LIFNR | BANKS, BANKL bank key/IFSC, BANKN account, KOINH holder |
| usage_12m | 146,266 | MATNR+WERKS | 12-month consumption value and qty (stands in for MSEG) |
| vendor_spend_12m | 20,024 | LIFNR+BUKRS | 12-month PO spend (stands in for EKKO/EKPO) |
| _defect_ledger | ~43K | rule+record | ground truth: injected / resolved dates (never used by rules) |
| _truth_*_entities | | | ground-truth entity id for ER evaluation |

Row counts vary slightly by seed/version; `run_pipeline.sh` prints them.

## Org units

| Plant | Name | Company code | Cross-border (HS/COO mandatory) |
|---|---|---|---|
| IN10 | Pune (Chakan) | 1000 | yes |
| IN20 | Silvassa | 1000 | no |
| IN30 | Chennai | 1000 | yes |
| TH10 | Rayong | 2000 | yes |
| PL10 | Poznań | 3000 | yes |
| DE10 | Neuss | 3100 | yes |
| US10 | Columbus OH | 4000 | no |
| MX10 | Querétaro | 5000 | yes |

## Rule catalogue

| Rule | Table | Dimension | Severity | Owner | Applies to | Fails when |
|---|---|---|---|---|---|---|
| M01 | MARA | Completeness | High | Product Data (PLM) | all materials | MATKL empty |
| M02 | MARA | Consistency | Medium | Product Data (PLM) | weights maintained | NTGEW > BRGEW |
| M03 | MARA | Completeness | Medium | Product Data (PLM) | weight > 0 | GEWEI empty |
| M04 | MARA | Validity | High | Product Data (PLM) | MATKL filled | MEINS not in allowed list for the group |
| M05 | MAKT | Validity | Low | Product Data (PLM) | English text exists | lower case, extra spaces, TEST/DUMMY/DO NOT USE |
| M06 | MAKT | Completeness | High | Product Data (PLM) | all materials | no SPRAS=E row |
| M07 | MARA | Completeness | High | Commercial | FERT | PRDHA empty |
| M08 | MARA | Validity | High | Commercial | FERT | EAN missing or check digit wrong |
| M09 | MARA | Consistency | Critical | Finance | stock > 0 | LVORM = X |
| M10 | MARA | Uniqueness | Critical | Product Data (PLM) | all materials | non-survivor in a Splink cluster |
| P01 | MARC | Consistency | High | Supply Planning | ROH/VERP/HIBE/ERSA | BESKZ = E |
| P02 | MARC | Consistency | High | Supply Planning | DISMM = VB | MINBE = 0 |
| P03 | MARC | Validity | High | Procurement | BESKZ F/X | PLIFZ = 0 or > 180 |
| P04 | MARC | Completeness | Medium | Supply Planning | DISMM PD/VB | DISPO empty |
| P05 | MARC | Completeness | Critical | Trade Compliance | ROH/FERT at cross-border plants | STAWN or HERKL empty |
| P06 | MBEW | Validity | Critical | Finance | VPRSV = S, stock > 0 | STPRS = 0 |
| P07 | MBEW | Accuracy | High | Finance | ROH/HALB/FERT/VERP, group ≥ 30 | price > 10× or < 0.1× median of (MATKL, plant) |
| P08 | MARC | Consistency | Medium | Supply Planning | MSTAE in OB/BL | MMSTA empty |
| V01 | LFA1 | Completeness | Critical | Indirect Tax | LAND1 = IN | STCD3 empty |
| V02 | LFA1 | Validity | Critical | Indirect Tax | IN with GSTIN | format, mod-36 checksum or state code ≠ REGIO |
| V03 | LFA1 | Validity | Medium | Procurement | all vendors | postcode empty or wrong country format |
| V04 | LFB1 | Completeness | High | Finance | company-code rows | ZTERM empty |
| V05 | LFBK | Consistency | Critical | Finance | vendors with bank | same account used by > 1 Splink entity |
| V06 | LFA1 | Completeness | Low | Procurement | all vendors | no phone and no email |
| V07 | LFA1 | Uniqueness | Critical | Procurement | all vendors | non-survivor in a Splink cluster |
| V08 | LFA1 | Consistency | Medium | Procurement | spend > 0 | SPERR = X |

Severity weights in scores: Critical 4 · High 3 · Medium 2 · Low 1.

## Main marts (`data/mdg.duckdb`, schema `marts`)

| Model | Grain | Use |
|---|---|---|
| fct_dq_results | rule × applicable record | base of every metric |
| fct_dq_exceptions | failing record | steward queue: owner, steward, SLA, age, breach |
| mart_dq_rule_scores | rule × org unit | pass rates |
| mart_dq_scorecard | slice | weighted scores by domain / org unit / owner / dimension |
| fct_dq_trend, mart_dq_trend_scores | month × rule × org unit | 12-month trend |
| mart_record_health | month × entity | fit-for-use rate |
| dq_reconciliation | rule | found vs ground truth |
| mart_sla_by_owner | owner × org unit × severity | SLA KPIs |
