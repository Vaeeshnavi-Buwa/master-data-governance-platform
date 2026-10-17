select LIFNR as lifnr, BUKRS as bukrs, cast(SPEND_12M_INR as double) as spend_inr
from {{ source('sap', 'vendor_spend_12m') }}
