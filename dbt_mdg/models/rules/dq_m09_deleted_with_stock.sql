-- M09: Flagged for deletion but stock on hand
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
with stock as (select matnr, sum(stock_qty) as qty, sum(stock_value_inr) as val from {{ ref('stg_mbew') }} group by 1)
{{ rule_output('M09', 'm.matnr', 'm.home_plant', 'm.created_on', "m.deletion_flag = 'X'", "'stock Rs ' || round(s.val, 0)") }}
from {{ ref('stg_mara') }} m
join stock s on s.matnr = m.matnr
where s.qty > 0
