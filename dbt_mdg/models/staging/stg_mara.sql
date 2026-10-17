select
    MATNR                          as matnr,
    MTART                          as mtart,
    MATKL                          as matkl,
    MEINS                          as meins,
    cast(BRGEW as double)          as brgew,
    cast(NTGEW as double)          as ntgew,
    nullif(trim(GEWEI), '')        as gewei,
    cast(ERSDA as date)            as created_on,
    ERNAM                          as created_by,
    split_part(ERNAM, '_', 2)      as home_plant,       -- creator's plant = accountable org unit
    LVORM                          as deletion_flag,
    MSTAE                          as xplant_status,
    PRDHA                          as prdha,
    EAN11                          as ean11,
    MFRPN                          as mfrpn,
    MFRNR                          as mfrnr,
    BISMT                          as old_matnr
from {{ source('sap', 'mara') }}
