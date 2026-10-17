-- P07: Price >10x or <0.1x of material-group median at the plant (groups >= 30)
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
with base as (
    select b.matnr, b.werks, b.unit_price, m.matkl, m.created_on,
           median(b.unit_price) over (partition by m.matkl, b.werks) as grp_median,
           count(*)             over (partition by m.matkl, b.werks) as grp_n
    from {{ ref('stg_mbew') }} b
    join {{ ref('stg_mara') }} m on m.matnr = b.matnr
    where m.mtart in ('ROH', 'HALB', 'FERT', 'VERP') and m.matkl is not null and b.unit_price > 0
)
{{ rule_output('P07', "matnr || '|' || werks", 'werks', 'created_on',
   'unit_price > 10 * grp_median or unit_price < 0.1 * grp_median',
   "'price ' || round(unit_price, 2) || ' vs median ' || round(grp_median, 2)") }}
from base
where grp_n >= 30
