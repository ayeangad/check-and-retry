#!/usr/bin/env bash
# Resumable overnight E2 run. Safe to re-run: finished episodes are skipped.
# Keeps the machine awake while running, lid closed included, via systemd-inhibit (released on exit).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOG=poc/results/e2_qwen3.5-4b.log

if ! curl -s localhost:8188/system_stats >/dev/null; then
  echo "starting ComfyUI..."
  setsid .venv/bin/python vendor/ComfyUI/main.py --cpu --listen 127.0.0.1 --port 8188 \
    --base-directory poc/comfy_base --disable-auto-launch --disable-api-nodes --disable-manager-ui \
    --dont-print-server > poc/results/comfyui.log 2>&1 &
  for i in $(seq 1 60); do curl -s localhost:8188/system_stats >/dev/null && break; sleep 2; done
fi
curl -s localhost:11434/api/tags >/dev/null || { echo "Ollama is not running (start it: ollama serve)"; exit 1; }

exec systemd-inhibit --what=sleep:idle:handle-lid-switch --who=atelier-e2 --why="E2 experiment running" \
  .venv/bin/python poc/experiments/run_e2.py --model qwen3.5:4b --seeds ${SEEDS:-0 1} \
    --arms base extended output_retry contract --out poc/results/e2_qwen3.5-4b.jsonl >> "$LOG" 2>&1
