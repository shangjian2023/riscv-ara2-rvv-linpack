#!/usr/bin/env bash
# Rebuild all E3 ELFs after adding -DSKIP_CHAIN=1, then resume the reduced
# priority queue. Do not resume if any build reports a warning/failure.
set -u
LOG=/root/cj_rebuild_fixed.log
CJ_CONFIGS="2_lanes 4_lanes 8_lanes 16_lanes" bash /root/cj_v2.sh > "$LOG" 2>&1
if grep -E '^\[W\]|FAILED' "$LOG"; then
  echo "E3 rebuild failed; priority queue NOT resumed $(date)"
  exit 1
fi
echo "E3 rebuild clean; starting fixed priority queue $(date)"
CJ_PAR=15 bash /root/cloud_priority.sh > /root/cpriority_fixed.log 2>&1
