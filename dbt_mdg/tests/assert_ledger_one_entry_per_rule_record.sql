-- Ground truth must not double count: one ledger entry per (rule, record).
select rule_id, record_key, count(*) from {{ ref('stg_defect_ledger') }}
group by 1, 2 having count(*) > 1
