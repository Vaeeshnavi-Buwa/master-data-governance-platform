-- P03: Planned delivery time 0 or >180 days on external procurement
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('P03', "c.matnr || '|' || c.werks", 'c.werks', 'm.created_on', 'c.plifz = 0 or c.plifz > 180', "'PLIFZ=' || c.plifz") }}
from {{ ref('stg_marc') }} c
join {{ ref('stg_mara') }} m on m.matnr = c.matnr
where c.beskz in ('F', 'X')
