-- M03: Weight maintained without weight unit
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('M03', 'm.matnr', 'm.home_plant', 'm.created_on', 'm.gewei is null', "'GEWEI=<null>'") }}
from {{ ref('stg_mara') }} m
where coalesce(m.brgew, 0) > 0 or coalesce(m.ntgew, 0) > 0
