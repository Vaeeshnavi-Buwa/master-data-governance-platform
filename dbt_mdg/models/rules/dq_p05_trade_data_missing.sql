-- P05: HS code or country of origin missing at a cross-border plant
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('P05', "c.matnr || '|' || c.werks", 'c.werks', 'm.created_on', 'c.hs_code is null or c.country_of_origin is null',
   "'HS=' || coalesce(c.hs_code, '<null>') || ' COO=' || coalesce(c.country_of_origin, '<null>')") }}
from {{ ref('stg_marc') }} c
join {{ ref('stg_mara') }} m on m.matnr = c.matnr
join {{ ref('org_units') }} o on o.org_unit = c.werks
where o.cross_border and m.mtart in ('ROH', 'FERT')
