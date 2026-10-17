select MATNR as matnr, WERKS as werks, cast(CONS_12M_VALUE as double) as consumption_value_inr,
       cast(CONS_12M_QTY as double) as consumption_qty
from {{ source('sap', 'usage_12m') }}
