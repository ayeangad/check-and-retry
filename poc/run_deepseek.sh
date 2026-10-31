#!/usr/bin/env bash
# Main run: DeepSeek V4.1 Flash (Hyde's own contestant), 73 long Exhibit-style briefs, 3 repeats, 4 arms.
# Resumable; hard spend cap enforced by poc/results/deepseek_spend.json.
cd "$(dirname "$0")/.."
curl -s localhost:8188/system_stats >/dev/null || { echo "ComfyUI not running: start it via poc/run_overnight.sh or README"; exit 1; }
exec .venv/bin/python poc/experiments/run_e2.py --backend deepseek --model deepseek-flash --cap-usd 2.0 \
  --briefs poc/tasks_long/briefs.jsonl --seeds ${SEEDS:-0 1 2} --arms base extended output_retry contract \
  --out poc/results/e2_deepseek_long.jsonl >> poc/results/e2_deepseek_long.log 2>&1
