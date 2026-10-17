-- M08: Finished good EAN/GTIN missing or check digit invalid
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('M08', 'm.matnr', 'm.home_plant', 'm.created_on', 'not ' ~ ean13_is_valid('m.ean11'), "coalesce(m.ean11, '<null>')") }}
from {{ ref('stg_mara') }} m
where m.mtart = 'FERT'
