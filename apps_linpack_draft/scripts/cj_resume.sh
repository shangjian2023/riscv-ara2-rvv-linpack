#!/usr/bin/env bash
# cj_resume.sh - run phase 3 (sims) + phase 4 (collect) of cloud_jobs.sh
# against an EXISTING jobs.txt + already-built ELFs. Skips builds entirely.
#
# Background: cloud_jobs.sh phase 3 used `xargs -I{} bash -c 'run_one "$@"' _`
# - GNU xargs 4.8 on the node does NOT append the input line when the
# template lacks a literal {}, so every job ran with an empty argument
# (rc=127 x102, zero sims). This resume uses an explicit {} in the template.
#
# Usage:  CJ_OUT=/root/work/ara/results/cloud2348 bash cj_resume.sh
set -uo pipefail
OUT="${CJ_OUT:?set CJ_OUT}"
JOBS="${CJ_JOBS:-$OUT/jobs.txt}"
MODELS="${CJ_MODELS:-/root/models}"
CJ_PAR="${CJ_PAR:-24}"
ARA=/root/work/ara
mkdir -p "$OUT"

run_one() {
  local line="$1"
  local NAME="${line%%|*}"; local rest="${line#*|}"
  local CFG="${rest%%|*}"
  local ELF="${rest#*|}"
  local wd="$OUT/$NAME"; mkdir -p "$wd"
  if [ -f "$wd/sim.log" ] && grep -q "Simulation statistics" "$wd/sim.log" 2>/dev/null; then
    echo "[skip] $NAME"; return 0
  fi
  (cd "$wd" && "$MODELS/$CFG.bin" +notrace -l "ram,$ELF,elf" > sim.log 2>&1)
  local rc=$?
  local rows=$(grep -cE '^(RES|CFG)' "$wd/sim.log" 2>/dev/null || true)
  echo "[$(date +%H:%M)] $NAME rc=$rc rows=$rows"
}
export -f run_one
export OUT MODELS

echo "== resume: $(wc -l < "$JOBS") jobs, par=$CJ_PAR =="
cat "$JOBS" | xargs -P "$CJ_PAR" -I{} bash -c 'run_one "{}"'
echo "== sims done $(date) =="

CSV="$OUT/cloud_all.csv"
echo "job,config,phase,var,mr,lmul,kc,pipe,N,cycles,fpcyc,util,chk" > "$CSV"
python3 - "$OUT" <<'PY'
import os, re, sys, csv
out = sys.argv[1]
rows = []
for name in sorted(os.listdir(out)):
    wd = os.path.join(out, name)
    log = os.path.join(wd, "sim.log")
    if not os.path.isdir(wd) or not os.path.isfile(log):
        continue
    cfg = name.split("_")[1] if "_" in name else "?"
    txt = open(log, errors="ignore").read()
    for m in re.finditer(r"^RES,phase=(\w+),var=([\w.]+)(?:,mr=(\d+),lmul=(\d+),kc=(\d+),pipe=(\d+))?,N=(\d+)(?:,nb=(\d+))?,cycles=(\d+),fpcyc=([\d.]+),util=([\d.]+)", txt, re.M):
        p, var, mr, lm, kc, pi, N, nb, cyc, fp, ut = m.groups()
        rows.append([name, cfg, p, var, mr or 0, lm or 0, kc or 0, pi or 0, N, cyc, fp, ut, ""])
    s = None
    for line in txt.splitlines():
        m = re.search(r"Calculating a \((\d+) x ", line)
        if m: s = m.group(1); continue
        m = re.search(r"execution took (\d+) cycles", line)
        if m and s: rows.append([name, cfg, "e0", "fmatmul", 0,0,0,0, s, m.group(1), "", "", ""])
with open(os.path.join(out, "cloud_all.csv"), "a", newline="") as f:
    csv.writer(f).writerows(rows)
print(f"collected {len(rows)} rows -> cloud_all.csv")
PY
echo "== RESUME COMPLETE =="
