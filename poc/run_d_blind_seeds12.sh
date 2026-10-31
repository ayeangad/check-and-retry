#!/usr/bin/env bash
# D13 extension (2026-10-31): D-B blind condition on seeds 1-2, ledger cap raised to $2.50.
set -euo pipefail
cd "$(dirname "$0")/.."
curl -s localhost:8188/system_stats >/dev/null || { echo "ComfyUI not running"; exit 1; }
exec .venv/bin/python poc/experiments/run_e2.py --backend deepseek --model deepseek-flash --cap-usd 2.5 \
  --briefs poc/tasks_long/briefs.jsonl --families t2i_logo edit_ref_logo --seeds 1 2 \
  --arms extended output_retry output_retry_rich contract \
  --out poc/results/d_blind.jsonl >> poc/results/d_blind.log 2>&1
