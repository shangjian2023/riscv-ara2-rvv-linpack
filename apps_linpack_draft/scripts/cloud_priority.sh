#!/usr/bin/env bash
# cloud_priority.sh - prioritized, reduced RTL matrix for the 15-core node.
#
# The two original xargs dispatchers must be SIGSTOPped before starting this
# script. Their already-running children continue normally and own their logs.
# This scheduler only starts jobs which are neither complete nor active, and
# caps the TOTAL number of running models (old + new) at CJ_PAR.
set -uo pipefail

ARA=/root/work/ara
OUT_A=$ARA/results/cloud2348
OUT_16=$ARA/results/cloud
JOBS_A=$OUT_A/jobs.txt
JOBS_16=$OUT_16/jobs.txt
MODELS=/root/models
CJ_PAR="${CJ_PAR:-15}"
QUEUE=/root/priority_jobs.txt

# Priority order: cheap paper anchors, likely-best kernels, full 2-lane sweep,
# remaining 4-lane anchors, E1 chains, then compiler comparison on 2 lanes.
# BIG and E7 at 4/8/16 lanes are intentionally omitted. E3 at 8/16 lanes is
# limited to mr8m2p0/mr8m2p1/mr4m1p0; 4 lanes adds mr2m1p0/mr16m2p0/mr8m4p0.
{
  grep -hE '^e0_' "$JOBS_A" "$JOBS_16"
  grep -hE '^e3_(2|4|8|16)_lanes_(mr8m2p0|mr8m2p1|mr4m1p0)\|' "$JOBS_A" "$JOBS_16"
  grep -hE '^e3_2_lanes_' "$JOBS_A"
  grep -hE '^e3_4_lanes_(mr2m1p0|mr16m2p0|mr8m4p0)\|' "$JOBS_A"
  grep -hE '^e1_' "$JOBS_A" "$JOBS_16"
  grep -hE '^e7_2_lanes_' "$JOBS_A"
} | awk -F'|' '!seen[$1]++' > /root/priority_selected.txt

: > "$QUEUE"
while IFS='|' read -r NAME CFG ELF; do
  [ -n "${NAME:-}" ] || continue
  case "$NAME" in *_16_lanes*) OUT=$OUT_16 ;; *) OUT=$OUT_A ;; esac
  LOG=$OUT/$NAME/sim.log
  if [ -f "$LOG" ] && grep -q 'Simulation statistics' "$LOG" 2>/dev/null; then
    echo "[done] $NAME"
    continue
  fi
  # Old runners retain ownership of active jobs. The ELF-only second grep
  # cannot self-match because the first grep requires a literal models/ path.
  if ps -eo args | grep '[m]odels/' | grep -Fq -- "$ELF,"; then
    echo "[hold] $NAME (already active)"
    continue
  fi
  printf '%s|%s|%s\n' "$NAME" "$CFG" "$ELF" >> "$QUEUE"
done < /root/priority_selected.txt

echo "== priority queue: $(wc -l < "$QUEUE") pending, total model cap=$CJ_PAR =="
exec 3< "$QUEUE"
exhausted=0
while :; do
  total=$(ps -eo args | grep -c '[m]odels/.*lanes.bin' || true)
  while [ "$total" -lt "$CJ_PAR" ] && [ "$exhausted" -eq 0 ]; do
    if ! IFS='|' read -r NAME CFG ELF <&3; then
      exhausted=1
      break
    fi
    case "$NAME" in *_16_lanes*) OUT=$OUT_16 ;; *) OUT=$OUT_A ;; esac
    wd=$OUT/$NAME
    mkdir -p "$wd"
    (
      cd "$wd" || exit 1
      "$MODELS/$CFG.bin" +notrace -l "ram,$ELF,elf" > sim.log 2>&1
      rc=$?
      rows=$(grep -cE '^(RES|CFG)' sim.log 2>/dev/null || true)
      echo "[$(date +%H:%M)] $NAME rc=$rc rows=$rows"
    ) &
    echo "[$(date +%H:%M)] launch $NAME (active=$total)"
    total=$((total + 1))
  done
  workers=$(jobs -pr | wc -l)
  if [ "$exhausted" -eq 1 ] && [ "$workers" -eq 0 ]; then
    break
  fi
  sleep 20
done
wait
echo "== PRIORITY COMPLETE $(date) =="
