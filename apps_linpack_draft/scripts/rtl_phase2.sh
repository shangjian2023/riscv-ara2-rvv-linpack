#!/usr/bin/env bash
# rtl_phase2.sh - complete the E1 dataset after the v2-scalar interruption.
#
# Background (2026-11-03): the default-mode 4_lanes linpack run was interrupted
# after 15.5h - v2_autovec at N=256 runs PURE SCALAR under the plain -O2 GCC
# build (no fast-math -> 0 vector instructions; 252M cycles = 8.7h for one
# kernel). Everything except the linpack-chain rows was already measured and
# salvaged into results/rtl/4_lanes/res.csv. This script completes the set:
#
#   1. re-verilate 4_lanes (the 16_lanes verilate was killed mid-flight - the
#      build dir cannot be trusted), run linpack with the sweep trimmed to
#      N=64 + SKIP_CHECK (chain N=512 unchanged), append phase=lp rows
#   2. verilate 16_lanes, run fmatmul 32^3/64^3 (paper anchors ARE 16-lane
#      numbers), run the same trimmed linpack
#   3. run e8_compare.py over the merged dataset
#
# The trimmed sweep rows (N=64) are ALSO appended to res.csv - same variant at
# a different N is a valid extra data point for e8, not a duplicate.
#
# Usage (WSL):  ARA_ROOT=/root/work/ara bash rtl_phase2.sh
set -uo pipefail

ARA_ROOT="${ARA_ROOT:-/root/work/ara}"
APP_DIR="$ARA_ROOT/apps"; HW_DIR="$ARA_ROOT/hardware"
OUT="${PH2_OUT:-$ARA_ROOT/results/rtl}"
MODEL="$HW_DIR/build/verilator/Vara_tb_verilator"
XGCC="/opt/xpack/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-"
SHIM="/root/work/shim-include"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LP_DEFINES="${PH2_LP_DEFINES:--DSKIP_CHECK=1 -DDGEMM_SWEEP_N=64}"
E8_MODEL="${E8_MODEL:-}"
mkdir -p "$OUT"

echo "== phase2: complete E1 dataset =="
echo "   trimmed defines: $LP_DEFINES"

build_linpack() { # $1=lanes $2=vlen
  make -C "$APP_DIR" bin/linpack COMPILER=gcc \
    RISCV_CC="${XGCC}gcc" RISCV_CXX="${XGCC}g++" \
    RISCV_OBJDUMP="${XGCC}objdump" RISCV_AR="${XGCC}ar" \
    RISCV_LD="${XGCC}ld" RISCV_STRIP="${XGCC}strip" RISCV_CC_GCC="${XGCC}gcc" \
    RISCV_FLAGS="-O2 -g -mcmodel=medany -march=rv64gcv -mabi=lp64d -ffreestanding -Icommon -I$SHIM -static -fno-common -fno-builtin-printf -ffunction-sections -fdata-sections -DNR_LANES=$1 -DVLEN=$2 $LP_DEFINES" \
    RISCV_CCFLAGS_GCC="-O2 -g -mcmodel=medany -march=rv64gcv -mabi=lp64d -ffreestanding -Icommon -I$SHIM -static -fno-common -fno-builtin-printf -ffunction-sections -fdata-sections -DNR_LANES=$1 -DVLEN=$2 $LP_DEFINES -std=gnu99" \
    RUNTIME_LLVM="common/crt0-gcc.S.o common/printf-gcc.c.o common/string-gcc.c.o common/serial-gcc.c.o common/util-gcc.c.o" \
    RISCV_LDFLAGS="-static -nostdlib -lm -lgcc -Wl,--gc-sections -T$APP_DIR/common/link.ld"
}

build_fmatmul() { # $1=lanes $2=vlen $3="M N P"
  make -C "$APP_DIR" bin/fmatmul COMPILER=gcc \
    RISCV_CC="${XGCC}gcc" RISCV_CXX="${XGCC}g++" \
    RISCV_OBJDUMP="${XGCC}objdump" RISCV_AR="${XGCC}ar" \
    RISCV_LD="${XGCC}ld" RISCV_STRIP="${XGCC}strip" RISCV_CC_GCC="${XGCC}gcc" \
    RISCV_FLAGS="-O2 -g -mcmodel=medany -march=rv64gcv -mabi=lp64d -ffreestanding -Icommon -I$SHIM -static -fno-common -fno-builtin-printf -ffunction-sections -fdata-sections -DNR_LANES=$1 -DVLEN=$2" \
    RISCV_CCFLAGS_GCC="-O2 -g -mcmodel=medany -march=rv64gcv -mabi=lp64d -ffreestanding -Icommon -I$SHIM -static -fno-common -fno-builtin-printf -ffunction-sections -fdata-sections -DNR_LANES=$1 -DVLEN=$2 -std=gnu99" \
    RUNTIME_LLVM="common/crt0-gcc.S.o common/printf-gcc.c.o common/string-gcc.c.o common/serial-gcc.c.o common/util-gcc.c.o" \
    RISCV_LDFLAGS="-static -nostdlib -lm -lgcc -Wl,--gc-sections -T$APP_DIR/common/link.ld" \
    def_args_fmatmul="\"$3\""
}

verilate_cfg() { # $1=config - force via touch (timestamps alone never trigger)
  echo "[V] verilate $1 (forced)"
  touch "$ARA_ROOT/config/$1.mk"
  make -C "$HW_DIR" verilate config="$1" > "$OUT/$1/verilate.log" 2>&1
}

run_sim() { # $1=app $2=log  (NEVER kill: buffered UART dies with the process)
  (cd "$HW_DIR" && ./build/verilator/Vara_tb_verilator +notrace \
     -l "ram,$APP_DIR/bin/$1,elf") > "$2" 2>&1
}

# ---------------------------------------------------------------- 4_lanes
CFG=4_lanes; L=4; V=4096; dir="$OUT/$CFG"; mkdir -p "$dir"
echo ""; echo "==== [$CFG] chain completion ===="
verilate_cfg "$CFG" || { echo "verilate failed"; exit 1; }
echo "[E1] building trimmed linpack ..."
build_linpack $L $V > "$dir/linpack_trim_build.log" 2>&1 \
  || { echo "BUILD FAILED (see $dir/linpack_trim_build.log)"; exit 1; }
echo "[E1] running trimmed linpack on RTL (~1-1.5h) ..."
run_sim linpack "$dir/linpack_trim.log" \
  && echo "  sim OK" || { echo "  SIM FAILED (see $dir/linpack_trim.log)"; exit 1; }
grep -E '^(CFG|RES|DONE)' "$dir/linpack_trim.log" >> "$dir/res.csv"
n_lp=$(grep -c 'RES,phase=lp' "$dir/linpack_trim.log" || true)
fails=$(grep -oE 'DONE,fails=[0-9]+' "$dir/linpack_trim.log" | grep -oE '[0-9]+' || echo "?")
echo "  $CFG: +$n_lp linpack-chain rows (fails=$fails) appended to res.csv"

# ---------------------------------------------------------------- 16_lanes
CFG=16_lanes; L=16; V=16384; dir="$OUT/$CFG"; mkdir -p "$dir"
echo ""; echo "==== [$CFG] E0 anchors + trimmed E1 ===="
verilate_cfg "$CFG" || { echo "verilate failed"; exit 1; }
for TRIPLE in "32 32 32" "64 64 64"; do
  A="${TRIPLE%% *}"
  echo "[E0] fmatmul $A ..."
  build_fmatmul $L $V "$TRIPLE" > "$dir/fmatmul_build_$A.log" 2>&1 \
    || { echo "  BUILD FAILED"; continue; }
  run_sim fmatmul "$dir/fmatmul_$A.log" || { echo "  SIM FAILED"; continue; }
  python3 - "$dir/fmatmul_$A.log" "$CFG" "$L" "$OUT/rtl_all.csv" <<'PY'
import re, sys
log, cfg, lanes, allcsv = sys.argv[1:5]
rows = []; s = None
for line in open(log, encoding="utf-8", errors="ignore"):
    m = re.search(r"Calculating a \((\d+) x (\d+)\) x \((\d+) x (\d+)\)", line)
    if m: s = int(m.group(1)); continue
    m = re.search(r"execution took (\d+) cycles", line)
    if m and s is not None: rows.append([s, m.group(1), None, None]); continue
    m = re.search(r"performance is ([\d.]+) FLOP/cycle \(([\d.]+)%", line)
    if m and rows and rows[-1][2] is None: rows[-1][2], rows[-1][3] = m.group(1), m.group(2)
    if "Passed." in line and rows: rows[-1].append("yes")
with open(allcsv, "a", encoding="utf-8") as f:
    for r in rows:
        if len(r) >= 4:
            f.write(f"{cfg},{lanes},fmatmul,{r[0]},{r[0]},{r[1]},{r[2]},{r[3]},"
                    f"{r[4] if len(r) > 4 else '?'}\n")
print(f"  fmatmul: {len(rows)} sizes parsed")
PY
done

echo "[E1] building trimmed linpack @16 ..."
build_linpack $L $V > "$dir/linpack_trim_build.log" 2>&1 \
  || { echo "BUILD FAILED"; exit 1; }
echo "[E1] running trimmed linpack @16 on RTL (~2-4h) ..."
run_sim linpack "$dir/linpack_trim.log" \
  && echo "  sim OK" || { echo "  SIM FAILED"; exit 1; }
grep -E '^(CFG|CHK|CHECK_PHASE|RES|DONE)' "$dir/linpack_trim.log" > "$dir/res.csv"
n=$(grep -c '^RES,' "$dir/linpack_trim.log" || true)
fails=$(grep -oE 'DONE,fails=[0-9]+' "$dir/linpack_trim.log" | grep -oE '[0-9]+' || echo "?")
echo "  $CFG: $n RES rows (fails=$fails) -> res.csv"

# ---------------------------------------------------------------- E8
echo ""; echo "== phase2 done =="
[ -n "$E8_MODEL" ] && python3 "$SCRIPT_DIR/e8_compare.py" --rtl-dir "$OUT" --model "$E8_MODEL" \
  || echo "(e8 skipped: set E8_MODEL, or run e8_compare.py manually)"
