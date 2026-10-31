#!/usr/bin/env bash
# Experiment D (2026-10-31): 37 logo briefs, seed 0, DeepSeek, same $2 cumulative cap.
#   D-B blind:    original briefs; extended / output_retry / output_retry_rich / contract (one shared prefix)
#   D-A informed: logo pixel size stated in the brief; base / extended / output_retry / contract
# Resumable: re-run to continue. Stops cleanly at the cap.
set -euo pipefail
cd "$(dirname "$0")/.."
curl -s localhost:8188/system_stats >/dev/null || { echo "ComfyUI not running"; exit 1; }
COMMON=(--backend deepseek --model deepseek-flash --cap-usd 2.0 --briefs poc/tasks_long/briefs.jsonl
        --families t2i_logo edit_ref_logo --seeds 0)
.venv/bin/python poc/experiments/run_e2.py "${COMMON[@]}" --arms extended output_retry output_retry_rich contract \
  --out poc/results/d_blind.jsonl >> poc/results/d_blind.log 2>&1
.venv/bin/python poc/experiments/run_e2.py "${COMMON[@]}" --state-logo-size --arms base extended output_retry contract \
  --out poc/results/d_informed.jsonl >> poc/results/d_informed.log 2>&1
