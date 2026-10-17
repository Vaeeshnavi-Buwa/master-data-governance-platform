-- Splink cluster + survivorship result per material
select c.MATNR as matnr, c.cluster_id, c.cluster_size, x.is_survivor, x.golden_matnr
from {{ source('er', 'er_material_clusters') }} c
join {{ source('er', 'xref_material') }} x using (MATNR)
