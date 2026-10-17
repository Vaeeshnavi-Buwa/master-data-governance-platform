-- Monthly weighted DQ score by slice (for the trend charts)
with overall as ({{ weighted_score(ref('fct_dq_trend'), ['month_end']) }}),
by_domain as ({{ weighted_score(ref('fct_dq_trend'), ['month_end', 'domain']) }}),
by_org as ({{ weighted_score(ref('fct_dq_trend'), ['month_end', 'org_unit']) }}),
by_owner as ({{ weighted_score(ref('fct_dq_trend'), ['month_end', 'owner_function']) }})
select month_end, 'overall' as slice_type, 'All' as slice_value, dq_score, checks, failures from overall
union all select month_end, 'domain', domain, dq_score, checks, failures from by_domain
union all select month_end, 'org_unit', org_unit, dq_score, checks, failures from by_org
union all select month_end, 'owner_function', owner_function, dq_score, checks, failures from by_owner
