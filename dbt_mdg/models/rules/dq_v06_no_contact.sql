-- V06: No phone and no email
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('V06', 'v.lifnr', 'v.home_bukrs', 'v.created_on', 'v.phone is null and v.email is null', "'no contact'") }}
from {{ ref('stg_lfa1') }} v
