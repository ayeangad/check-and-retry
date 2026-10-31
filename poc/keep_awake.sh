#!/usr/bin/env bash
# Hold a sleep/lid-switch inhibitor while the DeepSeek main run or the E4 queue is alive.
# The [x] bracket trick stops pgrep from matching this script's own command line.
exec systemd-inhibit --what=sleep:idle:handle-lid-switch --who=atelier-deepseek --why="DeepSeek E2/E4 running" \
  bash -c 'while pgrep -f "[r]un_e2.py --backend deepseek|[q]ueue_e4.sh|[r]un_e4_selection" >/dev/null; do sleep 60; done'
