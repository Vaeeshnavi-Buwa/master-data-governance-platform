-- V08: Posting-blocked vendor with spend in last 12 months
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
with sp as (select lifnr, sum(spend_inr) as spend from {{ ref('stg_vendor_spend_12m') }} group by 1)
{{ rule_output('V08', 'v.lifnr', 'v.home_bukrs', 'v.created_on', "v.posting_block = 'X'", "'spend Rs ' || round(sp.spend, 0)") }}
from {{ ref('stg_lfa1') }} v
join sp on sp.lifnr = v.lifnr
where sp.spend > 0
