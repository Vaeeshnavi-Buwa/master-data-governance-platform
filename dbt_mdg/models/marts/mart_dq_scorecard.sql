-- Current scorecard, long format: one row per (slice_type, slice_value)
with overall as ({{ weighted_score(ref('mart_dq_rule_scores'), []) }}),
by_domain as ({{ weighted_score(ref('mart_dq_rule_scores'), ['domain']) }}),
by_org as ({{ weighted_score(ref('mart_dq_rule_scores'), ['org_unit']) }}),
by_owner as ({{ weighted_score(ref('mart_dq_rule_scores'), ['owner_function']) }}),
by_dim as ({{ weighted_score(ref('mart_dq_rule_scores'), ['dimension']) }}),
by_org_domain as ({{ weighted_score(ref('mart_dq_rule_scores'), ['org_unit', 'domain']) }})
select 'overall' as slice_type, 'All' as slice_value, null as domain, * from overall
union all select 'domain', domain, domain, dq_score, checks, failures, rules_applied from by_domain
union all select 'org_unit', org_unit, null, dq_score, checks, failures, rules_applied from by_org
union all select 'owner_function', owner_function, null, dq_score, checks, failures, rules_applied from by_owner
union all select 'dimension', dimension, null, dq_score, checks, failures, rules_applied from by_dim
union all select 'org_unit_x_domain', org_unit, domain, dq_score, checks, failures, rules_applied from by_org_domain
