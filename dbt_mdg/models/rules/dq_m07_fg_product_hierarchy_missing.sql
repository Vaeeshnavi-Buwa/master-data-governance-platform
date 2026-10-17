-- M07: Finished good without product hierarchy
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('M07', 'm.matnr', 'm.home_plant', 'm.created_on', 'm.prdha is null', "'PRDHA=<null>'") }}
from {{ ref('stg_mara') }} m
where m.mtart = 'FERT'
