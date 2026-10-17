select * from {{ ref('mart_dq_scorecard') }} where dq_score < 0 or dq_score > 1
