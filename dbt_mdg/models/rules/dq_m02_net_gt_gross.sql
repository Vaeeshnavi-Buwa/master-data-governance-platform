-- M02: Net weight greater than gross weight
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('M02', 'm.matnr', 'm.home_plant', 'm.created_on', 'm.ntgew > m.brgew', "'NTGEW=' || m.ntgew || ' > BRGEW=' || m.brgew") }}
from {{ ref('stg_mara') }} m
where m.brgew is not null and m.ntgew is not null
