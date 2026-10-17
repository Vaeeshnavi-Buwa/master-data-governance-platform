select
    MATNR as matnr, BWKEY as werks, VPRSV as price_control,
    cast(STPRS as double) as standard_price, cast(VERPR as double) as moving_price,
    case when VPRSV = 'S' then cast(STPRS as double) else cast(VERPR as double) end as unit_price,
    cast(LBKUM as double) as stock_qty, cast(SALK3 as double) as stock_value_inr
from {{ source('sap', 'mbew') }}
