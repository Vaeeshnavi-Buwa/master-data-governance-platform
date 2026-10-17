# Master Data Governance Operating Model: Kestrel Flexibles

*Version 1.0 · effective 1 April 2026 · owner: Head of Master Data Governance*

## 1. Purpose and scope

Master data (materials, plant/MRP data, valuation, vendors) is a shared company asset. This model defines **who owns it, who fixes it, how fast, and who decides when owners disagree**. It covers SAP tables MARA, MAKT, MARC, MBEW, LFA1, LFB1 and LFBK across 8 plants and 6 company codes. Customer master and BOMs/routings are phase 2.

**Principles**
1. Every attribute has exactly one accountable **data owner** (a business function, not IT).
2. Quality is built in at creation (workflow validation, search-before-create), not cleaned afterwards.
3. Everything is measured: 26 rules, scored daily, published monthly, priced in rupees.
4. Fix the most expensive defects first (cost-ranked backlog, not ticket order).

## 2. Roles

| Role | Who | Accountable for |
|---|---|---|
| **Executive sponsor** | CFO | Funding, final escalation, sets annual DQ targets |
| **Data Governance Council** | CFO (chair), VP Supply Chain, VP Operations, CPO, VP Sales, Head of MDG | Approves standards and rule changes, resolves cross-function disputes, reviews scorecard monthly |
| **Head of Master Data Governance** | 1 FTE (central) | Runs the programme, owns the platform, rule catalogue and scorecard, chairs the working group |
| **Data owners** (7) | Heads of PLM, Sales Ops, Supply Planning, Procurement, Financial Controller, EXIM, Indirect Tax | Accountable for their attributes' quality; approve standards; sign off exceptions |
| **Plant data stewards** (8) | 50% role per plant | Fix exceptions in their queue within SLA; first line for creation requests |
| **Central MDM analysts** (3) | Central team | Create/change requests, duplicate merges, steward review queue, rule development |
| **Data custodian** | SAP / IT | System controls, workflow, authorisations, extracts; never decides business content |

## 3. Attribute ownership (who owns what)

| Attribute group | SAP fields | Data owner | Rules |
|---|---|---|---|
| Basic data: material group, UoM, weights, descriptions | MARA-MATKL/MEINS/BRGEW/NTGEW/GEWEI, MAKT | Product Data (PLM) | M01–M06, M10 |
| Commercial: product hierarchy, EAN/GTIN | MARA-PRDHA/EAN11 | Commercial | M07, M08 |
| MRP: MRP type, controller, reorder point, procurement type, plant status | MARC-DISMM/DISPO/MINBE/BESKZ/MMSTA | Supply Planning | P01, P02, P04, P08 |
| Purchasing: planned delivery time | MARC-PLIFZ | Procurement | P03 |
| Foreign trade: HS code, country of origin | MARC-STAWN/HERKL | Trade Compliance | P05 |
| Valuation: price control, standard price, deletion with stock | MBEW, MARA-LVORM | Finance | M09, P06, P07 |
| Vendor general data, contacts, duplicates, blocks | LFA1 | Procurement | V03, V06, V07, V08 |
| Vendor tax: GSTIN | LFA1-STCD3 | Indirect Tax | V01, V02 |
| Vendor payment and bank data | LFB1-ZTERM, LFBK | Finance | V04, V05 |

## 4. RACI

R = Responsible (does it) · A = Accountable (signs off) · C = Consulted · I = Informed

| Activity | Council | Head of MDG | Data owner | Plant steward | MDM analyst | SAP/IT |
|---|---|---|---|---|---|---|
| Set data standards and rules | A | R | C | C | C | I |
| Add / change a DQ rule | A | R | C | I | R | C |
| Create or change a material | I | I | A | R (request) | R (execute) | I |
| Create or change a vendor (incl. bank) | I | I | A (Procurement; bank: Finance) | R (request) | R (execute + call-back) | I |
| Fix an exception in the queue | I | I | A | R | C | I |
| Merge duplicates (auto band ≥ 0.95) | I | A | I | I | R | C |
| Merge duplicates (review band 0.5–0.95) | I | I | A | C | R | I |
| Resolve a cross-function dispute | A | R | C | I | I | I |
| Publish the monthly scorecard | I | A | I | I | R | C |
| Maintain workflow, controls, extracts | I | C | I | I | I | R/A |

## 5. Service levels

SLA clocks start when the exception first appears in the daily run. Legacy backlog (defects that existed before go-live) is burned down by a separate plan, cost-ranked, and is **not** counted against SLAs.

| Severity | Examples | Fix within | Escalate at |
|---|---|---|---|
| **Critical** | HS code missing at cross-border plant, duplicate material/vendor, GSTIN missing/invalid, bank account shared with unrelated vendor, deleted material with stock, standard price 0 with stock | **5 working days** | Day 6 → data owner; day 11 → Council member |
| **High** | Reorder point 0 on VB, wrong UoM, delivery time 0/>180, missing product hierarchy/EAN, price outlier | **10 working days** | Day 11 → data owner |
| **Medium** | Weight unit missing, net > gross, no MRP controller, status inconsistency | **20 working days** | Monthly scorecard |
| **Low** | Naming convention, contact data | **30 working days** | Quarterly clean-up |

**Service levels for requests:** material create 2 working days (1 for urgent production), vendor create 3 working days (bank changes only after call-back to a number already on file, never to one given in the request).

**Programme KPIs (published monthly):**

| KPI | Baseline Mar 2026 | Sep 2026 | Target Mar 2027 |
|---|---|---|---|
| Weighted DQ score | 95.3% | 97.7% | ≥ 98.5% |
| Materials fit for use | 50.8% | 69.5% | ≥ 85% |
| Vendors fit for use | 73.7% | 82.8% | ≥ 92% |
| Critical rules ≥ 98% pass (rule × org unit) | — | 28 below | 0 below |
| New defects fixed within SLA | — | tracked | ≥ 90% |
| Annual cost of poor data (P50) | — | ₹25.4 Cr | ≤ ₹12 Cr |

## 6. Escalation path

1. **Steward** fixes within SLA, or flags "needs owner decision" in the queue.
2. **Data owner** decides within 5 working days (e.g., which HS code applies; whether two vendors really are one legal entity).
3. **Head of MDG** mediates when two owners disagree (e.g., Supply Planning wants a new material, PLM says it duplicates an existing one).
4. **Council** decides at the next meeting, or by circulation within 48 hours for Critical items blocking a shipment or payment.
5. **CFO** has the final word; decisions are logged as standards.

Hard rules that do not wait for escalation: a vendor bank change without call-back is rejected; a material flagged for deletion that still has stock is reversed.

## 7. Governance cadence

| Forum | Frequency | Attendees | Inputs | Outputs |
|---|---|---|---|---|
| Daily run | Daily 06:00 | automated | SAP extract | GX gate result, refreshed scores and queues |
| Steward stand-up | Weekly, 30 min per region | Stewards, MDM analysts | Exception queue by age and ₹ | Assignments, blockers |
| Data owner review | Fortnightly, 45 min | Each owner + Head of MDG | Owner scorecard, SLA breaches, review-band pairs | Decisions, standard change requests |
| **Data Governance Council** | **Monthly, 60 min** | Council | Scorecard, trend, top-10 costliest rules, escalations | Decisions, targets, funding |
| Rule and threshold calibration | Quarterly | Head of MDG, analysts, owners | 300 labelled review pairs, rule false-positive log | Updated Splink thresholds, rule changes |
| Programme review | Twice a year | CFO, Council | Cost model refresh with finance-validated inputs | Budget, scope for phase 2 |

**Council agenda (standing, 60 min):** scorecard & trend (10) · top-10 rules by ₹ and owner actions (15) · escalations needing a decision (20) · standards/rule changes for approval (10) · next month's focus (5).

## 8. Preventive controls (quality at source)

1. **Search-before-create:** every create request is scored against existing materials/vendors with the Splink model; a match ≥ 0.5 requires the requester to justify a new record.
2. **Create-workflow validation:** the same dbt rule logic runs as validation in the request form (mandatory HS code at cross-border plants, UoM from the allowed list, GSTIN checksum, EAN check digit).
3. **Four-eyes on bank data:** requester ≠ approver; call-back mandatory.
4. **Deletion guardrail:** a deletion flag is blocked while stock or open orders exist.

## 9. How a rule is added or changed

1. Owner or steward raises a request with the business case (₹ impact, example records).
2. MDM analyst writes the rule model in dbt + an entry in `dq_rule_catalog` (severity, owner, dimension, cost driver) and tests it on the current extract (false-positive review of 50 records).
3. Council approves; the rule goes live in "observe" mode for one month (visible, not counted in scores), then counts.
4. All changes go through version control; the commit history is the audit trail.
