-- M04: Base UoM not allowed for material group (governance standard in seed material_group_uom)
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('M04', 'm.matnr', 'm.home_plant', 'm.created_on', 'u.allowed_uom is null', "m.matkl || ' in ' || m.meins") }}
from {{ ref('stg_mara') }} m
left join {{ ref('material_group_uom') }} u on u.matkl = m.matkl and u.allowed_uom = m.meins
where m.matkl is not null
