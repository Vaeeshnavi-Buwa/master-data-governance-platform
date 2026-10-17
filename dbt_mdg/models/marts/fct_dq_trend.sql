-- Monthly rule x org-unit history. Past months are replayed from the defect ledger
-- (demo backfill); the current month is the live measurement from fct_dq_results.
-- Population for past months = applicable records created on or before month end.
{% set snap = "date '" ~ var('snapshot_date') ~ "'" %}
with months as (
    select (d + interval 1 month - interval 1 day)::date as month_end
    from range(date '{{ var("window_start") }}', date_trunc('month', {{ snap }}), interval 1 month) t(d)
),
pop as (
    select m.month_end, r.rule_id, r.org_unit, count(*) as population
    from months m
    join {{ ref('fct_dq_results') }} r on r.created_on <= m.month_end
    group by all
),
fails as (
    select m.month_end, l.rule_id, l.org_unit, count(*) as failures
    from months m
    join {{ ref('stg_defect_ledger') }} l
      on l.injected_date <= m.month_end and (l.resolved_date is null or l.resolved_date > m.month_end)
    group by all
),
history as (
    select p.month_end, p.rule_id, p.org_unit, p.population, least(coalesce(f.failures, 0), p.population) as failures,
           'ledger_backfill' as source
    from pop p left join fails f using (month_end, rule_id, org_unit)
),
current_month as (
    select {{ snap }} as month_end, rule_id, org_unit, population, failures, 'live_measurement' as source
    from {{ ref('mart_dq_rule_scores') }}
)
select t.*, c.domain, c.dimension, c.severity, c.severity_weight, c.owner_function
from (select * from history union all select * from current_month) t
join {{ ref('dq_rule_catalog') }} c using (rule_id)
