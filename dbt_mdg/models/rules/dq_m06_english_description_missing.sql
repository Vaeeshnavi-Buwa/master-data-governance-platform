-- M06: English description missing
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('M06', 'm.matnr', 'm.home_plant', 'm.created_on', 't.matnr is null', "'no SPRAS=E row'") }}
from {{ ref('stg_mara') }} m
left join {{ ref('stg_makt') }} t on t.matnr = m.matnr and t.spras = 'E'
