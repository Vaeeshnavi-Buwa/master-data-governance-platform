-- The steward work queue: every failing record with owner, steward, SLA and age.
{% set snap = "date '" ~ var('snapshot_date') ~ "'" %}
with first_seen as (      -- in production: first dbt snapshot in which the exception appeared
    select rule_id, record_key, min(injected_date) as first_seen
    from {{ ref('stg_defect_ledger') }}
    where resolved_date is null
    group by 1, 2
)
select
    r.rule_id, r.record_key, r.org_unit, o.org_name, o.region, r.domain, r.dimension, r.severity,
    r.owner_function, d.data_owner_role, d.escalation_to,
    r.org_unit || ' ' || r.domain || ' Data Steward'                         as data_steward,
    r.failing_value, c.description as rule_description, c.cost_driver,
    coalesce(f.first_seen, {{ snap }})                                        as first_seen,
    -- legacy backlog starts its SLA clock at programme go-live, not on the day it was created
    greatest(coalesce(f.first_seen, {{ snap }}), date '{{ var("program_start") }}') as sla_clock_start,
    case r.severity when 'Critical' then 5 when 'High' then 10 when 'Medium' then 20 else 30 end as sla_days,
    date_diff('day', greatest(coalesce(f.first_seen, {{ snap }}), date '{{ var("program_start") }}'), {{ snap }}) as age_days,
    date_diff('day', greatest(coalesce(f.first_seen, {{ snap }}), date '{{ var("program_start") }}'), {{ snap }})
      > case r.severity when 'Critical' then 5 when 'High' then 10 when 'Medium' then 20 else 30 end as sla_breached,
    coalesce(f.first_seen, {{ snap }}) < date '{{ var("program_start") }}'    as is_legacy_backlog
from {{ ref('fct_dq_results') }} r
join {{ ref('dq_rule_catalog') }} c using (rule_id)
left join {{ ref('org_units') }} o on o.org_unit = r.org_unit
left join {{ ref('data_owners') }} d on d.owner_function = r.owner_function
left join first_seen f on f.rule_id = r.rule_id and f.record_key = r.record_key
where r.is_fail
