-- P01: Bought-in material type set to in-house production
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('P01', "c.matnr || '|' || c.werks", 'c.werks', 'm.created_on', "c.beskz = 'E'", "m.mtart || ' BESKZ=E'") }}
from {{ ref('stg_marc') }} c
join {{ ref('stg_mara') }} m on m.matnr = c.matnr
where m.mtart in ('ROH', 'VERP', 'HIBE', 'ERSA')
