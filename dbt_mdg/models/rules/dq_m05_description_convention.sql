-- M05: English description violates naming convention (upper case, single spaces, no placeholders)
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('M05', 'm.matnr', 'm.home_plant', 'm.created_on',
   "regexp_matches(t.maktx, '[a-z]') or t.maktx <> trim(t.maktx) or t.maktx like '%  %' or regexp_matches(t.maktx, '\\b(TEST|DO NOT USE|DUMMY)\\b')",
   "'[' || t.maktx || ']'") }}
from {{ ref('stg_mara') }} m
join {{ ref('stg_makt') }} t on t.matnr = m.matnr and t.spras = 'E'
