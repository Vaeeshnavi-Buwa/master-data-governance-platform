-- V07: Duplicate vendor - non-surviving member of a Splink cluster
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('V07', 'v.lifnr', 'v.home_bukrs', 'v.created_on', 'e.cluster_size > 1 and not e.is_survivor', "'duplicate of ' || e.golden_lifnr") }}
from {{ ref('stg_lfa1') }} v
join {{ ref('stg_er_vendor') }} e on e.lifnr = v.lifnr
