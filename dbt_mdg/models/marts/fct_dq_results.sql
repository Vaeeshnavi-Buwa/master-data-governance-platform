-- All rule results, one row per (rule, applicable record). The single table every
-- score, trend and SLA metric is derived from. Add a rule = add a model + list it here.
{{ config(materialized='table') }}
with unioned as (
select * from {{ ref('dq_m01_material_group_missing') }}
union all
select * from {{ ref('dq_m02_net_gt_gross') }}
union all
select * from {{ ref('dq_m03_weight_unit_missing') }}
union all
select * from {{ ref('dq_m04_uom_not_allowed') }}
union all
select * from {{ ref('dq_m05_description_convention') }}
union all
select * from {{ ref('dq_m06_english_description_missing') }}
union all
select * from {{ ref('dq_m07_fg_product_hierarchy_missing') }}
union all
select * from {{ ref('dq_m08_fg_ean_invalid') }}
union all
select * from {{ ref('dq_m09_deleted_with_stock') }}
union all
select * from {{ ref('dq_m10_duplicate_material') }}
union all
select * from {{ ref('dq_p01_bought_in_as_inhouse') }}
union all
select * from {{ ref('dq_p02_reorder_point_zero') }}
union all
select * from {{ ref('dq_p03_delivery_time_invalid') }}
union all
select * from {{ ref('dq_p04_mrp_controller_missing') }}
union all
select * from {{ ref('dq_p05_trade_data_missing') }}
union all
select * from {{ ref('dq_p06_standard_price_zero') }}
union all
select * from {{ ref('dq_p07_price_outlier') }}
union all
select * from {{ ref('dq_p08_plant_status_inconsistent') }}
union all
select * from {{ ref('dq_v01_gstin_missing') }}
union all
select * from {{ ref('dq_v02_gstin_invalid') }}
union all
select * from {{ ref('dq_v03_postcode_invalid') }}
union all
select * from {{ ref('dq_v04_payment_terms_missing') }}
union all
select * from {{ ref('dq_v05_bank_shared_unrelated') }}
union all
select * from {{ ref('dq_v06_no_contact') }}
union all
select * from {{ ref('dq_v07_duplicate_vendor') }}
union all
select * from {{ ref('dq_v08_blocked_vendor_with_spend') }}
)
select u.*, c.domain, c.dimension, c.severity, c.severity_weight, c.owner_function, c.detection_method
from unioned u
join {{ ref('dq_rule_catalog') }} c using (rule_id)
