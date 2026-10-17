select MATNR as matnr, SPRAS as spras, MAKTX as maktx
from {{ source('sap', 'makt') }}
