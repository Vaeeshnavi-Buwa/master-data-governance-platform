select LIFNR as lifnr, BUKRS as bukrs, AKONT as recon_account, ZTERM as payment_terms, ZWELS as payment_methods
from {{ source('sap', 'lfb1') }}
