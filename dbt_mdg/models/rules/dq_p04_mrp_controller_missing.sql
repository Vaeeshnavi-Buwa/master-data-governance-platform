-- P04: MRP-planned material without MRP controller
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('P04', "c.matnr || '|' || c.werks", 'c.werks', 'm.created_on', 'c.dispo is null', "'DISPO=<null>'") }}
from {{ ref('stg_marc') }} c
join {{ ref('stg_mara') }} m on m.matnr = c.matnr
where c.dismm in ('PD', 'VB')
