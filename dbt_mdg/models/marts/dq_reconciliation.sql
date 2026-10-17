-- DQ rule validation against ground truth. ONE metric family: "did the rule flag the right RECORDS?"
-- (Pairwise entity-resolution accuracy is a different question and lives in er_metrics.json /
--  the ER panel - never compare the two numbers directly.)
--
-- Basis per rule type:
--   ledger_key  : deterministic rules + V05. Expected = distinct open ledger keys; a flag is correct
--                 if the same (rule, record_key) is open in the ledger.
--   dup_surplus : M10 / V07 (duplicate records to retire). Which member of a cluster is retired is a
--                 survivorship CHOICE, so we don't require the flagged record to be the one the
--                 generator created last. Expected = sum over true entities of (records - 1);
--                 correct = sum over true entities of min(flagged members, records - 1).
with found as (
    select distinct rule_id, record_key from {{ ref('fct_dq_results') }} where is_fail
),
truth as (
    select distinct rule_id, record_key from {{ ref('stg_defect_ledger') }}
    where resolved_date is null and rule_id not in ('M10', 'V07')
),
ledger_basis as (
    select coalesce(t.rule_id, f.rule_id) as rule_id,
           count(t.record_key)                                   as expected_defects,
           count(f.record_key)                                   as flagged,
           count(case when t.record_key is not null and f.record_key is not null then 1 end) as correct
    from truth t
    full outer join (select * from found where rule_id not in ('M10', 'V07')) f
      on t.rule_id = f.rule_id and t.record_key = f.record_key
    group by 1
),
er_truth as (
    select 'M10' as rule_id, MATNR as record_key, entity_id from {{ source('history', '_truth_material_entities') }}
    union all
    select 'V07', LIFNR, entity_id from {{ source('history', '_truth_vendor_entities') }}
),
er_entity as (
    select e.rule_id, e.entity_id, count(*) - 1 as surplus, count(f.record_key) as flagged_members
    from er_truth e
    left join found f on f.rule_id = e.rule_id and f.record_key = e.record_key
    group by 1, 2
),
dup_basis as (
    select rule_id,
           sum(surplus)                           as expected_defects,
           (select count(*) from found f where f.rule_id = er_entity.rule_id) as flagged,
           sum(least(flagged_members, surplus))   as correct
    from er_entity group by 1
),
unioned as (
    select *, 'ledger_key' as metric_basis from ledger_basis
    union all
    select *, 'dup_surplus' from dup_basis
)
select c.rule_id, c.detection_method, u.metric_basis,
       coalesce(u.expected_defects, 0)                         as expected_defects,
       coalesce(u.flagged, 0)                                  as flagged,
       coalesce(u.correct, 0)                                  as correct,
       coalesce(u.expected_defects, 0) - coalesce(u.correct, 0) as missed,
       coalesce(u.flagged, 0) - coalesce(u.correct, 0)          as extra,
       round(u.correct / nullif(u.flagged, 0)::double, 4)         as dq_precision,
       round(u.correct / nullif(u.expected_defects, 0)::double, 4) as dq_recall
from {{ ref('dq_rule_catalog') }} c
left join unioned u using (rule_id)
order by c.rule_id
