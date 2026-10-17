-- M01: Material group (MATKL) missing
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('M01', 'm.matnr', 'm.home_plant', 'm.created_on', 'm.matkl is null', "'MATKL=<null>'") }}
from {{ ref('stg_mara') }} m
