{#
  DQ score of a slice = severity-weighted mean of rule pass rates, where each rule's
  pass rate is computed WITHIN the slice. Weighting stops 10,000 cosmetic
  description issues from hiding 50 blocked-GSTIN vendors.
#}
{% macro weighted_score(rule_stats_relation, group_cols) -%}
with r as (
    select {{ group_cols | join(', ') }}{% if group_cols %},{% endif %} rule_id, max(severity_weight) as w,
           sum(population) as pop, sum(failures) as fails
    from {{ rule_stats_relation }}
    group by {{ (group_cols + ['rule_id']) | join(', ') }}
)
select {{ group_cols | join(', ') }}{% if group_cols %},{% endif %}
       round(sum(w * (1 - fails / pop::double)) / sum(w), 4) as dq_score,
       sum(pop) as checks, sum(fails) as failures, count(*) as rules_applied
from r
where pop > 0
{% if group_cols %}group by {{ group_cols | join(', ') }}{% endif %}
{%- endmacro %}
