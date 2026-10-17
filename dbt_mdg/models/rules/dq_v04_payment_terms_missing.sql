-- V04: Payment terms missing in company code
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('V04', "b.lifnr || '|' || b.bukrs", 'b.bukrs', 'v.created_on', 'b.payment_terms is null', "'ZTERM=<null>'") }}
from {{ ref('stg_lfb1') }} b
join {{ ref('stg_lfa1') }} v on v.lifnr = b.lifnr
