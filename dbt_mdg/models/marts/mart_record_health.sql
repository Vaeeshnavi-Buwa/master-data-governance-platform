-- "Fit-for-use" rate: share of master records with ZERO open defects across all rules.
-- This is the KPI a COO understands ("1 in 6 materials can't be used without a fix"),
-- complementary to the weighted rule score.
{% set snap = "date '" ~ var('snapshot_date') ~ "'" %}
with base as (      -- every record, keyed at entity level (material or vendor)
    select 'Material' as entity, matnr as entity_key, home_plant as org_unit, created_on from {{ ref('stg_mara') }}
    union all
    select 'Vendor', lifnr, home_bukrs, created_on from {{ ref('stg_lfa1') }}
),
live as (
    select distinct case when domain = 'Vendor' then 'Vendor' else 'Material' end as entity,
           split_part(record_key, '|', 1) as entity_key
    from {{ ref('fct_dq_results') }} where is_fail
),
months as (
    select (d + interval 1 month - interval 1 day)::date as month_end
    from range(date '{{ var("window_start") }}', date_trunc('month', {{ snap }}), interval 1 month) t(d)
    union all select {{ snap }}
),
hist as (
    select distinct m.month_end,
           case when l.rule_id like 'V%' then 'Vendor' else 'Material' end as entity,
           split_part(l.record_key, '|', 1) as entity_key
    from months m
    join {{ ref('stg_defect_ledger') }} l
      on l.injected_date <= m.month_end and (l.resolved_date is null or l.resolved_date > m.month_end)
    where m.month_end < {{ snap }}
),
dirty as (
    select month_end, entity, entity_key from hist
    union all
    select {{ snap }}, entity, entity_key from live
)
select m.month_end, b.entity,
       count(*)                                         as records,
       count(d.entity_key)                              as records_with_defects,
       round(1 - count(d.entity_key) / count(*)::double, 4) as fit_for_use_rate
from months m
join base b on b.created_on <= m.month_end
left join dirty d on d.month_end = m.month_end and d.entity = b.entity and d.entity_key = b.entity_key
group by all
order by 2, 1
