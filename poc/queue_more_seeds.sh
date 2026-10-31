#!/usr/bin/env bash
# Wait for the running E2 job to finish, then run seeds 2 and 3 (seeds 0/1 are skipped as already done).
cd "$(dirname "$0")/.."
while pgrep -f "experiments/run_e2.py --model" >/dev/null; do sleep 60; done
echo "--- queued seeds 2,3 starting $(date) ---" >> poc/results/e2_qwen3.5-4b.log
SEEDS="0 1 2 3" exec poc/run_overnight.sh
