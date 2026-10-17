-- Business threshold, not a bug: Critical rules should pass >= 98%.
-- severity=warn -> shows in the run log and the council pack, doesn't break the build.
{{ config(severity='warn') }}
select rule_id, org_unit, pass_rate
from {{ ref('mart_dq_rule_scores') }}
where severity = 'Critical' and pass_rate < 0.98
