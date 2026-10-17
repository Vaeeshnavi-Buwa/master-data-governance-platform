-- Rule x org-unit pass rates (the atoms every score is built from)
select
    rule_id, org_unit, domain, dimension, severity, severity_weight, owner_function, detection_method,
    count(*)                                  as population,
    sum(case when is_fail then 1 else 0 end)  as failures,
    1 - sum(case when is_fail then 1 else 0 end) / count(*)::double as pass_rate
from {{ ref('fct_dq_results') }}
group by all
