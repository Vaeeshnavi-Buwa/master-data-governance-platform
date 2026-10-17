-- V05: Bank account shared by vendors that are NOT the same entity (Splink clusters)
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
with acct as (
    select k.bank_key, k.bank_account, count(distinct e.cluster_id) as entities
    from {{ ref('stg_lfbk') }} k
    join {{ ref('stg_er_vendor') }} e on e.lifnr = k.lifnr
    group by 1, 2
)
{{ rule_output('V05', 'v.lifnr', 'v.home_bukrs', 'v.created_on', 'a.entities > 1', "k.bank_key || '/' || k.bank_account || ' used by ' || a.entities || ' entities'") }}
from {{ ref('stg_lfbk') }} k
join {{ ref('stg_lfa1') }} v on v.lifnr = k.lifnr
join acct a on a.bank_key = k.bank_key and a.bank_account = k.bank_account
