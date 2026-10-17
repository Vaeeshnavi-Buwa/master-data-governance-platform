select LIFNR as lifnr, BANKS as bank_country, BANKL as bank_key, BANKN as bank_account, KOINH as account_holder
from {{ source('sap', 'lfbk') }}
