-- M10: Duplicate material - non-surviving member of a Splink cluster
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('M10', 'm.matnr', 'm.home_plant', 'm.created_on', 'e.cluster_size > 1 and not e.is_survivor', "'duplicate of ' || e.golden_matnr") }}
from {{ ref('stg_mara') }} m
join {{ ref('stg_er_material') }} e on e.matnr = m.matnr
