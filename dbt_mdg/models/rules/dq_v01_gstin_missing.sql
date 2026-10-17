-- V01: Indian vendor without GSTIN
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('V01', 'v.lifnr', 'v.home_bukrs', 'v.created_on', 'v.gstin is null', "'STCD3=<null>'") }}
from {{ ref('stg_lfa1') }} v
where v.land1 = 'IN'
