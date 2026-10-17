-- Every deterministic rule must flag exactly the open defects in the ledger:
-- nothing missed (dq_recall = 1), nothing invented (dq_precision = 1).
select * from {{ ref('dq_reconciliation') }}
where detection_method = 'deterministic' and (missed <> 0 or extra <> 0)
