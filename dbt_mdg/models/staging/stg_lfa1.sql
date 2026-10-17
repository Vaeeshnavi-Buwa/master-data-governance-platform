select
    LIFNR as lifnr, NAME1 as name1, STRAS as street, ORT01 as city, nullif(trim(PSTLZ), '') as postcode,
    REGIO as regio, LAND1 as land1, TELF1 as phone, SMTP_ADDR as email, nullif(trim(STCD3), '') as gstin,
    STCEG as vat_reg, KTOKK as account_group, SPERR as posting_block, LOEVM as deletion_flag,
    cast(ERDAT as date) as created_on, ERNAM as created_by, split_part(ERNAM, '_', 2) as home_bukrs
from {{ source('sap', 'lfa1') }}
