-- P06: Standard price 0 with stock on hand
-- Grain: one row per APPLICABLE record. is_fail = the record breaks the rule.
{{ rule_output('P06', "b.matnr || '|' || b.werks", 'b.werks', 'm.created_on', 'b.standard_price = 0', "'STPRS=0, stock qty ' || b.stock_qty") }}
from {{ ref('stg_mbew') }} b
join {{ ref('stg_mara') }} m on m.matnr = b.matnr
where b.price_control = 'S' and b.stock_qty > 0
