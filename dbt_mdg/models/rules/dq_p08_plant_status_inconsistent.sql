-- P08: Plant status active while cross-plant status blocked/obsolete
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('P08', "c.matnr || '|' || c.werks", 'c.werks', 'm.created_on', 'c.plant_status is null', "'MSTAE=' || m.xplant_status || ' MMSTA=<null>'") }}
from {{ ref('stg_marc') }} c
join {{ ref('stg_mara') }} m on m.matnr = c.matnr
where m.xplant_status in ('OB', 'BL')
