select rule_id, record_key, plant as org_unit, cast(injected_date as date) as injected_date,
       cast(resolved_date as date) as resolved_date
from {{ source('history', '_defect_ledger') }}
