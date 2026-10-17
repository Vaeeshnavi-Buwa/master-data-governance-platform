select c.LIFNR as lifnr, c.cluster_id, c.cluster_size, x.is_survivor, x.golden_lifnr
from {{ source('er', 'er_vendor_clusters') }} c
join {{ source('er', 'xref_vendor') }} x using (LIFNR)
