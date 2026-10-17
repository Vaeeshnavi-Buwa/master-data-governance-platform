select
    MATNR as matnr, WERKS as werks, DISMM as dismm, DISPO as dispo, BESKZ as beskz, EKGRP as ekgrp,
    cast(PLIFZ as int) as plifz, cast(MINBE as double) as minbe, cast(EISBE as double) as eisbe,
    MMSTA as plant_status, PRCTR as prctr, STAWN as hs_code, HERKL as country_of_origin
from {{ source('sap', 'marc') }}
