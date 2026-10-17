-- V03: Postal code missing or invalid for country
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('V03', 'v.lifnr', 'v.home_bukrs', 'v.created_on', 'v.postcode is null or not regexp_full_match(v.postcode, f.regex)', "coalesce(v.postcode, '<null>') || ' (' || v.land1 || ')'") }}
from {{ ref('stg_lfa1') }} v
left join {{ ref('postal_formats') }} f on f.land1 = v.land1
