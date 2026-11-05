#!/usr/bin/env bash
# cloud_jobs.sh - run the full RTL experiment matrix on the cloud node.
#
# Node prerequisites (already staged by cloud_a.sh / cloud_b2.sh):
#   /opt/verilator           Verilator 5.047 built on glibc 2.35 (chroot)
#   /opt/xpack               xPack riscv-none-elf-gcc 15.2
#   /usr/local/bin/bender    bender 0.32.1
#   /root/work/ara           repo+deps WITH local patches (L2 32MB, +notrace,
#                            verilate -O3), apps/linpack = latest main.c
#   /root/work/apps_linpack_draft  our scripts (this file's siblings)
#
# Phases:
#   1. verilate 2/4/8/16 lanes once each, stash the model binaries
#   2. full make build per (config x app-kind) to populate object caches;
#      E3 variant ELIs are then produced by recompiling main.c ONLY and
#      relinking by hand (7s each instead of a 90s full make)
#   3. fan out sims: E0 anchors, E1 trimmed, E3 26-variant x 4 cfg,
#      E7 gcc-combos x 4 cfg, BIG chain x 4 cfg  (~136 jobs, CJ_PAR wide)
#   4. collect every log into results/cloud/ and emit cloud_all.csv
#
# Usage:  bash cloud_jobs.sh            # from anywhere on the node
#         CJ_PAR=32 bash cloud_jobs.sh  # wider fan-out
set -uo pipefail

XPACK=/opt/xpack/xpack-riscv-none-elf-gcc-15.2.0-1
export PATH=/opt/verilator/bin:$XPACK/bin:/usr/local/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
ARA=/root/work/ara; APP=$ARA/apps; HW=$ARA/hardware
OUT=$ARA/results/cloud; EL=/root/elobjs; MODELS=/root/models
CJ_PAR="${CJ_PAR:-24}"
CONFIGS="${CJ_CONFIGS:-2_lanes 4_lanes 8_lanes 16_lanes}"
LOCK=$APP/.build.lock
mkdir -p "$OUT" "$EL" "$MODELS"
exec 9>"$LOCK"   # fd 9 = global build lock

lv() { local c="${1%_lanes}"; echo "${c##*/}"; }   # 4_lanes -> 4

echo "== cloud_jobs: $(date) | configs=[$CONFIGS] par=$CJ_PAR =="
verilator --version || { echo "FATAL: verilator not runnable"; exit 1; }
$XPACK/bin/riscv-none-elf-gcc --version | head -1 || { echo "FATAL: xpack gcc"; exit 1; }

# --- build helpers (validated GCC recipe; see rtl_collect.sh notes) ----------
SHIM=/root/work/shim-include
gcc_flags() { # lanes vlen extra-defines
  # -I paths ABSOLUTE: these flags are used both under `make -C $APP` (cwd =
  # apps, relative would work) and by fast_link's direct gcc calls (cwd is
  # wherever the driver was started from - relative -Icommon would miss
  # runtime.h and fail every variant link).
  echo "-O2 -g -mcmodel=medany -march=rv64gcv -mabi=lp64d -ffreestanding \
-I$APP/common -I$SHIM -static -fno-common -fno-builtin-printf \
-ffunction-sections -fdata-sections -DNR_LANES=$1 -DVLEN=$2 $3"
}
RUNTIME="common/crt0-gcc.S.o common/printf-gcc.c.o common/string-gcc.c.o common/serial-gcc.c.o common/util-gcc.c.o"
LDFLAGS="-static -nostdlib -lm -lgcc -Wl,--gc-sections -T$APP/common/link.ld"

app_clean() {
  rm -f "$APP"/bin/linpack "$APP"/bin/fmatmul
  find "$APP/linpack" "$APP/fmatmul" -name '*.o' -delete 2>/dev/null || true
  rm -f "$APP/common/"*-gcc.o "$APP/common/link.ld" \
        "$APP/linpack/data.S" "$APP/linpack/data.S.o" \
        "$APP/fmatmul/data.S" "$APP/fmatmul/data.S.o" 2>/dev/null || true
}

# make_build <app> <lanes> <vlen> <defines> <extra make args...>
make_build() {
  local app=$1 L=$2 V=$3 defs=$4; shift 4
  flock 9
  app_clean
  make -C "$APP" "bin/$app" COMPILER=gcc \
    RISCV_CC="$XPACK/bin/riscv-none-elf-gcc" RISCV_CXX="$XPACK/bin/riscv-none-elf-g++" \
    RISCV_OBJDUMP="$XPACK/bin/riscv-none-elf-objdump" RISCV_AR="$XPACK/bin/riscv-none-elf-ar" \
    RISCV_LD="$XPACK/bin/riscv-none-elf-ld" RISCV_STRIP="$XPACK/bin/riscv-none-elf-strip" \
    RISCV_CC_GCC="$XPACK/bin/riscv-none-elf-gcc" \
    RISCV_FLAGS="$(gcc_flags "$L" "$V" "$defs")" \
    RISCV_CCFLAGS_GCC="$(gcc_flags "$L" "$V" "$defs") -std=gnu99" \
    RUNTIME_LLVM="$RUNTIME" RISCV_LDFLAGS="$LDFLAGS" "$@" \
    > "$OUT/build_$app.last.log" 2>&1
  local rc=$?
  flock -u 9
  return $rc
}

# fast_link <name> <lanes> <vlen> <only-defines>  (E3 variant ELFs)
# Reuses the object cache from the last full make_build of linpack; only
# main.c is recompiled (ONLY_* macros affect main.c alone), then relinked
# by hand exactly like the make link rule.
fast_link() {
  local name=$1 L=$2 V=$3 defs=$4
  flock 9
  local f="$(gcc_flags "$L" "$V" "$defs") -std=gnu99"
  local objs="" rt="" o
  for o in $(find "$APP/linpack" -name '*.o' | sort); do
    case "$o" in */main.c.o) ;; *) objs="$objs $o" ;; esac
  done
  # RUNTIME is a space-separated list: prefix each word (quoting the whole
  # expansion would pass it to the linker as ONE giant path with spaces).
  for o in $RUNTIME; do rt="$rt $APP/$o"; done
  $XPACK/bin/riscv-none-elf-gcc -I"$APP/include" $f -c "$APP/linpack/main.c" \
      -o "$EL/tmp.main.o" \
   && $XPACK/bin/riscv-none-elf-gcc -I"$APP/include" $f -o "$EL/$name.elf" \
        "$EL/tmp.main.o" $objs $rt $LDFLAGS
  local rc=$?
  flock -u 9
  return $rc
}

# ------------------------------------------------- phase 1: verilate + stash
sed -i 's/make -j2 OPT_FAST/make -j32 OPT_FAST/' "$HW/Makefile"
for CFG in $CONFIGS; do
  [ -x "$MODELS/$CFG.bin" ] && { echo "[V] $CFG cached"; continue; }
  echo "[V] verilating $CFG ..."
  touch "$ARA/config/$CFG.mk"
  if ! make -C "$HW" verilate config="$CFG" > "$OUT/verilate_$CFG.log" 2>&1; then
    echo "[V] FAILED ($CFG) - see $OUT/verilate_$CFG.log"; exit 1
  fi
  cp "$HW/build/verilator/Vara_tb_verilator" "$MODELS/$CFG.bin"
done

# ------------------------------------------------- phase 2: builds + job list
JOBS=$OUT/jobs.txt; : > "$JOBS"
BIG_DEFS="-DBIG=1 -DSKIP_CHECK=1 -DDGEMM_SWEEP_N=132 -DSKIP_CHAIN=1"
E1_DEFS="-DSKIP_CHECK=1 -DDGEMM_SWEEP_N=64"           # chain stays ON
E3_DEFS="-DSKIP_CHECK=1 -DDGEMM_SWEEP_N=256 -DSKIP_CHAIN=1"

for CFG in $CONFIGS; do
  L=$(lv "$CFG"); V=$((1024 * L))
  # E0: fmatmul anchors (full make each; 2 per config)
  for TRIPLE in "32 32 32" "64 64 64"; do
    A="${TRIPLE%% *}"
    make_build fmatmul "$L" "$V" "" def_args_fmatmul="\"$TRIPLE\"" \
      && cp "$APP/bin/fmatmul" "$EL/fmatmul_${CFG}_$A.elf" \
      && echo "e0_${CFG}_$A|$CFG|$EL/fmatmul_${CFG}_$A.elf" >> "$JOBS" \
      || echo "[W] fmatmul $CFG $A build failed"
  done
  # E1: trimmed linpack with chain (one full make per config)
  make_build linpack "$L" "$V" "$E1_DEFS" \
    && cp "$APP/bin/linpack" "$EL/e1_${CFG}.elf" \
    && echo "e1_$CFG|$CFG|$EL/e1_$CFG.elf" >> "$JOBS" \
    || { echo "[W] e1 $CFG build failed"; continue; }
  # E3: one make_build per variant. (An object-cache fast-link scheme was
  # tried and abandoned: the apps Makefile `rm`s every intermediate .o after
  # linking, so nothing persists to relink against - see git history.)
  for PIPE in 0 1; do
    for MR in 2 4 8 16; do
      for LMUL in 1 2 4 8; do
        case $MR in 2|4) ;; 8) [ $LMUL -le 4 ] || continue ;; 16) [ $LMUL -le 2 ] || continue ;; esac
        N="e3_${CFG}_mr${MR}m${LMUL}p${PIPE}"
        make_build linpack "$L" "$V" "-DSKIP_CHECK=1 -DDGEMM_SWEEP_N=256 -DONLY_MR=$MR -DONLY_LMUL=$LMUL -DONLY_PIPE=$PIPE" \
          && cp "$APP/bin/linpack" "$EL/$N.elf" \
          && echo "$N|$CFG|$EL/$N.elf" >> "$JOBS" \
          || echo "[W] $N build failed"
      done
    done
  done
  # E7: gcc combos (node has no clang; clang side runs on WSL later)
  for COMBO in "gcc-O2-novec|-O2 -fno-tree-vectorize" "gcc-O3-novec|-O3 -fno-tree-vectorize" \
               "gcc-O3-fast-vec|-O3 -ffast-math" "gcc-O2-fast-vec|-O2 -ffast-math"; do
    TAG="${COMBO%%|*}"; FL="${COMBO#*|}"
    D="-DE7_MODE=1 -DDGEMM_SWEEP_N=132 -DSCALAR_N=128 $FL"
    make_build linpack "$L" "$V" "$D" \
      && cp "$APP/bin/linpack" "$EL/e7_${CFG}_${TAG}.elf" \
      && echo "e7_${CFG}_${TAG}|$CFG|$EL/e7_${CFG}_${TAG}.elf" >> "$JOBS" \
      || echo "[W] e7 $CFG $TAG build failed"
  done
  # BIG: chain N=1024, sweep suppressed
  make_build linpack "$L" "$V" "$BIG_DEFS" \
    && cp "$APP/bin/linpack" "$EL/big_${CFG}.elf" \
    && echo "big_$CFG|$CFG|$EL/big_${CFG}.elf" >> "$JOBS" \
    || echo "[W] big $CFG build failed"
done

NJ=$(wc -l < "$JOBS")
echo "== phase 2 done: $NJ jobs queued =="

# ------------------------------------------------- phase 3: parallel sims
run_one() { # jobline = name|config|elf
  IFS='|' read -r NAME CFG ELF <<< "$1"
  local wd="$OUT/$NAME"; mkdir -p "$wd"
  [ -f "$wd/sim.log" ] && grep -q "DONE\|Simulation statistics" "$wd/sim.log" 2>/dev/null && { echo "[skip] $NAME"; return 0; }
  (cd "$wd" && "$MODELS/$CFG.bin" +notrace -l "ram,$ELF,elf" > sim.log 2>&1)
  local rc=$?
  local res=$(grep -cE '^(RES|CFG)' "$wd/sim.log" 2>/dev/null || true)
  echo "[$(date +%H:%M)] $NAME rc=$rc rows=$res"
  return $rc
}
export -f run_one; export OUT MODELS

cat "$JOBS" | xargs -P "$CJ_PAR" -I{} bash -c 'run_one "$@"' _
echo "== phase 3 done =="

# ------------------------------------------------- phase 4: collect
CSV=$OUT/cloud_all.csv
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
    # fmatmul rows
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
echo "== cloud_jobs COMPLETE $(date) =="
echo "   results: $OUT/cloud_all.csv  (tar with: tar -C $ARA/results -czf cloud.tgz cloud)"
