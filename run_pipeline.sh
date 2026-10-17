#!/usr/bin/env bash
# End-to-end run: ~3 minutes on a laptop. Each step is idempotent.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data/reports
echo "== 0. governance reference data -> dbt seeds";   python src/00_export_seeds.py
echo "== 1. synthetic SAP extract";                     python src/01_generate_data.py
echo "== 2. Great Expectations landing gate";           python src/02_validate_landing_gx.py
echo "== 3. Splink entity resolution + golden records"; python src/03_entity_resolution.py > data/reports/er_log.txt 2>&1 && tail -n 40 data/reports/er_log.txt | grep -E "f1|precision|recall" | head -8
echo "== 4. dbt: rules, scores, trend, tests";          (cd dbt_mdg && dbt build --profiles-dir .)
echo "== 5. cost of poor data (Monte Carlo)";           python src/05_cost_model.py
echo "== 6. dashboard";                                 python src/06_build_dashboard.py
echo "Done. Open dashboard/standalone.html"
