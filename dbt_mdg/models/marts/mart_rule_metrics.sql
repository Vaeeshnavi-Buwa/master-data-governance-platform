-- One row per rule with every count EXPLICITLY named, so nobody compares apples with pairs.
--   applicable_rows   rows at the rule's grain the rule applies to
--   failing_rows      rows at that grain that fail (material x plant for MARC/MBEW rules, etc.)
--   impacted_entities distinct materials / vendors behind the failing rows
--   expected_defects / flagged / correct / dq_precision / dq_recall  -> see dq_reconciliation
select
    s.rule_id,
    case when c.table_name in ('MARC', 'MBEW') then 'material x plant'
         when c.table_name = 'LFB1' then 'vendor x company code'
         when c.domain = 'Vendor' then 'vendor'
         else 'material' end                                        as row_grain,
    s.applicable_rows, s.failing_rows,
    round(1 - s.failing_rows / s.applicable_rows::double, 4)          as pass_rate,
    s.impacted_entities,
    r.metric_basis, r.expected_defects, r.flagged, r.correct, r.dq_precision, r.dq_recall
from (
    select rule_id, count(*) as applicable_rows,
           count(*) filter (where is_fail) as failing_rows,
           count(distinct split_part(record_key, '|', 1)) filter (where is_fail) as impacted_entities
    from {{ ref('fct_dq_results') }} group by 1
) s
join {{ ref('dq_rule_catalog') }} c using (rule_id)
left join {{ ref('dq_reconciliation') }} r using (rule_id)
