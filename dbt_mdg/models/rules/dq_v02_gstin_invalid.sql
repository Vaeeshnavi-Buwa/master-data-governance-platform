-- V02: GSTIN fails format, checksum or state-code check
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('V02', 'v.lifnr', 'v.home_bukrs', 'v.created_on',
   '(not ' ~ gstin_is_valid('v.gstin') ~ ') or s.gst_state_code is distinct from substr(v.gstin, 1, 2)',
   "v.gstin || ' (region ' || coalesce(v.regio, '?') || ')'") }}
from {{ ref('stg_lfa1') }} v
left join {{ ref('india_gst_states') }} s on s.regio = v.regio
where v.land1 = 'IN' and v.gstin is not null
