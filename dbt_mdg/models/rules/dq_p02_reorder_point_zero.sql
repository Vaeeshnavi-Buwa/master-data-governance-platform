-- P02: Reorder-point planning with reorder point 0
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('P02', "c.matnr || '|' || c.werks", 'c.werks', 'm.created_on', 'coalesce(c.minbe, 0) = 0', "'MINBE=0'") }}
from {{ ref('stg_marc') }} c
join {{ ref('stg_mara') }} m on m.matnr = c.matnr
where c.dismm = 'VB'
