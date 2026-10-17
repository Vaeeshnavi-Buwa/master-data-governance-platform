{#
  Reusable validators. Written in SQL (not Python UDFs) so they run inside the
  warehouse and can be reused by any rule, dashboard or ad-hoc query.
#}

{# GSTIN: 15 chars, pattern, and the official mod-36 check character #}
{% macro gstin_is_valid(col) -%}
coalesce(
  regexp_full_match({{ col }}, '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')
  and substr({{ col }}, 15, 1) = substr('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',
      ((36 - (list_sum(list_transform(range(1, 15), lambda i:
            ((instr('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ', substr({{ col }}, i, 1)) - 1) * (case when i % 2 = 0 then 2 else 1 end)) // 36
          + ((instr('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ', substr({{ col }}, i, 1)) - 1) * (case when i % 2 = 0 then 2 else 1 end)) % 36
      )) % 36)) % 36)::bigint + 1, 1)
, false)
{%- endmacro %}

{# EAN-13 / GTIN-13 check digit #}
{% macro ean13_is_valid(col) -%}
coalesce(
  regexp_full_match({{ col }}, '^[0-9]{13}$')
  and cast(substr({{ col }}, 13, 1) as int) =
      (10 - (list_sum(list_transform(range(1, 13), lambda i:
          cast(substr({{ col }}, i, 1) as int) * (case when i % 2 = 0 then 3 else 1 end))) % 10)) % 10
, false)
{%- endmacro %}

{# Standard select-list every rule model returns: one row per APPLICABLE record #}
{% macro rule_output(rule_id, record_key, org_unit, created_on, fail_expr, detail) -%}
select
    '{{ rule_id }}'            as rule_id,
    {{ record_key }}           as record_key,
    {{ org_unit }}             as org_unit,
    {{ created_on }}           as created_on,
    coalesce({{ fail_expr }}, false) as is_fail,
    {{ detail }}               as failing_value
{%- endmacro %}
