{# keep schema names clean: staging / dq_rules / marts / reference (no target prefix) #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
