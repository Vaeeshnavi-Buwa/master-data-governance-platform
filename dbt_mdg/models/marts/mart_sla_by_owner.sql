-- Operating-model KPI: open exceptions and SLA breaches per data owner / steward
select owner_function, data_owner_role, escalation_to, org_unit, data_steward, severity, is_legacy_backlog,
       count(*) as open_exceptions,
       sum(case when sla_breached then 1 else 0 end) as sla_breached,
       round(avg(age_days), 1) as avg_age_days
from {{ ref('fct_dq_exceptions') }}
group by all
