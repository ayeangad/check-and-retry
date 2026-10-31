#!/usr/bin/env bash
# After the main DeepSeek run exits, run E4 (best-of-4 selection) with whatever budget remains under the cap.
cd "$(dirname "$0")/.."
while pgrep -f "run_e2.py --backend deepseek" >/dev/null; do sleep 60; done
exec .venv/bin/python poc/experiments/run_e4_selection.py --n 4 --out poc/results/e4_selection.jsonl >> poc/results/e4_selection.log 2>&1
