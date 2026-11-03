#!/usr/bin/env bash
# e7_run.sh - Experiment E7: compiler comparison on RTL (Ara2 / Verilator).
#
# Builds the linpack app under a matrix of {compiler} x {optimization flags},
# runs each binary on the SAME verilated Ara model, and archives binaries,
# disassembly, and sim logs. Summaries are produced by e7_summarize.py.
#
# Matrix (8 combos):
#   clang-O2-novec      LLVM -O2, no fast-math, auto-vec OFF
#                       (repo default: -O3 -ffast-math -fno-vectorize)
#   clang-O3-novec      LLVM -O3, no fast-math, auto-vec OFF
#   clang-O3-fast-vec   LLVM -O3 -ffast-math + -fvectorize (auto-vec ON)
#   clang-O2-fast-vec   LLVM -O2 -ffast-math + -fvectorize
#   gcc-O2-novec        GCC -O2, -fno-tree-vectorize
#   gcc-O3-novec        GCC -O3, -fno-tree-vectorize
#   gcc-O3-fast-vec     GCC -O3 -ffast-math (reduction auto-vec enabled)
#   gcc-O2-fast-vec     GCC -O2 -ffast-math
#
# What is measured per combo (RTL cycles via mcycle, config fixed):
#   v0_scalar           scalar baseline codegen
#   v2_autovec          auto-vectorized blocked kernel  <- the main event
#   rvv mr4m1 / mr8m2   hand-written intrinsics under each compiler's
#                       scheduling/register allocation (VRF spill differences)
#
# Usage (WSL; `make verilate` must have succeeded once for the chosen config):
#   cd <ara>/apps && bash <path-to>/e7_run.sh
#   E7_CONFIG=16_lanes bash <path-to>/e7_run.sh
#   E7_GCC_PREFIX=/opt/riscv/bin/riscv64-unknown-elf- bash <path>/e7_run.sh
#
# Outputs (default <ara>/results/e7/):
#   <tag>/{linpack.elf,linpack.dump,build.log,sim.log,res.csv}
#   build_status.csv   per-combo build/run status (failures are findings too)
#   e7_summary.csv + e7_report.md   via e7_summarize.py
#
# Implementation notes:
# * CLANG combos append flags AFTER the repo defaults via ENV_DEFINES (make
#   pastes them at the end of RISCV_CCFLAGS) - later flags win, so -O2 beats
#   the default -O3 and -fvectorize beats the repo's -fno-vectorize.
# * GCC combos must REPLACE the LLVM-specific defaults (-mllvm, zvfh march,
#   lld are not GCC-compatible), so RISCV_FLAGS is overridden wholesale and
#   -DNR_LANES/-DVLEN are re-added by this script (parsed from config name).
# * Every combo force-rebuilds app + runtime objects: stale .o files from a
#   previous combo would silently poison the comparison.
set -uo pipefail

# ---------------------------------------------------------------- locate ara
if [ -n "${ARA_ROOT:-}" ]; then
  :
elif [ -d "$(pwd)/hardware" ] && [ -d "$(pwd)/apps" ]; then
  ARA_ROOT="$(pwd)"
elif [ -d "$(pwd)/../hardware" ] && [ -d "$(pwd)/../apps" ]; then
  ARA_ROOT="$(cd .. && pwd)"          # run from <ara>/apps
else
  echo "error: run from <ara>/ or <ara>/apps/, or set ARA_ROOT" >&2
  exit 1
fi
APP_DIR="$ARA_ROOT/apps"
HW_DIR="$ARA_ROOT/hardware"
OUT="${E7_OUT:-$ARA_ROOT/results/e7}"
CONFIG="${E7_CONFIG:-4_lanes}"
SWEEP_N="${E7_SWEEP_N:-256}"
SCALAR_N="${E7_SCALAR_N:-128}"
REPS="${E7_REPS:-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$OUT"

# lanes/VLEN from config name (config/<L>_lanes.mk -> L lanes, VLEN=1024*L)
LANES="${CONFIG%_lanes}"; LANES="${LANES##*/}"
VLEN=$((1024 * LANES))

# ---------------------------------------------------------------- toolchains
# clang: repo-built first; else Ubuntu clang-18 with the xPack newlib/libgcc
# (validated: --target=riscv64-unknown-elf + xPack imafdc/lp64d multilib
# archives link clean under lld - the two compilers then share the same libc
# libs, which is what makes the E7 comparison fair).
CLANG_KIND=none
CLANG_BIN="${E7_CLANG:-}"
if [ -z "$CLANG_BIN" ] && [ -x "$ARA_ROOT/install/riscv-llvm/bin/clang" ]; then
  CLANG_BIN="$ARA_ROOT/install/riscv-llvm/bin/clang"; CLANG_KIND=repo
fi
if [ -z "$CLANG_BIN" ] && command -v clang-18 >/dev/null 2>&1; then
  CLANG_BIN="clang-18"; CLANG_KIND=clang18
fi
[ -n "$CLANG_BIN" ] && [ -x "$CLANG_BIN" ] || CLANG_BIN=""

GCC_PREFIX=""
XPACK="${E7_XPACK:-/opt/xpack/xpack-riscv-none-elf-gcc-15.2.0-1}"
for p in "${E7_GCC_PREFIX:-}" \
         "$ARA_ROOT/install/riscv-gcc/bin/riscv64-unknown-elf-" \
         "/opt/xpack/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-" \
         "riscv64-unknown-elf-" "riscv64-linux-gnu-"; do
  [ -n "$p" ] || continue
  if command -v "${p}gcc" >/dev/null 2>&1; then GCC_PREFIX="$p"; break; fi
done

echo "== E7 compiler matrix =="
echo "   ara root : $ARA_ROOT"
echo "   config   : $CONFIG (L=$LANES, VLEN=$VLEN)"
echo "   clang    : ${CLANG_BIN:-NOT FOUND} (${CLANG_KIND})"
echo "   gcc      : ${GCC_PREFIX:-NOT FOUND}${GCC_PREFIX:+gcc}"
echo "   out      : $OUT"

# ---------------------------------------------------------------- flag sets
# clang: append after repo defaults (later flags win)
clang_env() {
  echo "-DE7_MODE=1 -DDGEMM_SWEEP_N=$SWEEP_N -DSCALAR_N=$SCALAR_N -DSWEEP_REPS=$REPS $1"
}
# gcc: full replacement of RISCV_FLAGS/RISCV_CCFLAGS_GCC (repo defaults are
# LLVM-only). Validated recipe: -nostdlib (gcc driver otherwise adds -lc
# -lgloss, absent without newlib), real -lgcc, stub/real -lm, gcc-suffixed
# runtime objects swapped in via RUNTIME_LLVM (the link template hardcodes it).
SHIM="${E7_SHIM:-/root/work/shim-include}"
gcc_flags() {
  echo "-mcmodel=medany -march=rv64gcv -mabi=lp64d -ffreestanding -Icommon -I$SHIM \
-static -fno-common -fno-builtin-printf -ffunction-sections -fdata-sections \
-DNR_LANES=$LANES -DVLEN=$VLEN -DE7_MODE=1 -DDGEMM_SWEEP_N=$SWEEP_N \
-DSCALAR_N=$SCALAR_N -DSWEEP_REPS=$REPS $1"
}
GCC_LDFLAGS="-static -nostdlib -lm -lgcc -Wl,--gc-sections -T$APP_DIR/common/link.ld"
GCC_RUNTIME="common/crt0-gcc.S.o common/printf-gcc.c.o common/string-gcc.c.o common/serial-gcc.c.o common/util-gcc.c.o"

COMBOS=(
  "clang-O2-novec|clang|-O2 -fno-fast-math"
  "clang-O3-novec|clang|-fno-fast-math"
  "clang-O3-fast-vec|clang|-fvectorize"
  "clang-O2-fast-vec|clang|-O2 -fvectorize"
  "gcc-O2-novec|gcc|-O2 -fno-tree-vectorize"
  "gcc-O3-novec|gcc|-O3 -fno-tree-vectorize"
  "gcc-O3-fast-vec|gcc|-O3 -ffast-math"
  "gcc-O2-fast-vec|gcc|-O2 -ffast-math"
)

# ---------------------------------------------------------------- helpers
app_clean() {
  # force rebuild: drop binary, app objects, runtime objects, generated files
  rm -f "$APP_DIR"/bin/linpack "$APP_DIR"/bin/linpack.dump
  find "$APP_DIR/linpack" -name '*.o' -delete 2>/dev/null || true
  rm -f "$APP_DIR"/common/*-llvm.o "$APP_DIR"/common/*-gcc.o \
        "$APP_DIR"/common/link.ld "$APP_DIR"/linpack/data.S \
        "$APP_DIR"/linpack/data.S.o 2>/dev/null || true
}

build_one() { # $1=compiler $2=extra-flags
  if [ "$1" = clang ]; then
    if [ "$CLANG_KIND" = repo ]; then
      # repo clang: repo default flag chain, append after (later flags win)
      make -C "$APP_DIR" bin/linpack ENV_DEFINES="$(clang_env "$2")"
    else
      # Ubuntu clang-18: wholesale flags (--target + xPack newlib headers) and
      # a -nostdlib link line naming the xPack multilib archives explicitly
      local nl="$XPACK/riscv-none-elf/lib/rv64imafdc_zicsr_zaamo_zalrsc/lp64d"
      local lg="$XPACK/lib/gcc/riscv-none-elf/15.2.0/rv64imafdc_zicsr_zaamo_zalrsc/lp64d"
      local f="-march=rv64gcv_zfh_zvfh -mabi=lp64d -mno-relax -fuse-ld=lld \
--target=riscv64-unknown-elf -I$XPACK/riscv-none-elf/include -mcmodel=medany \
-Icommon -O3 -ffast-math -fno-common -fno-builtin-printf \
-ffunction-sections -fdata-sections -DNR_LANES=$LANES -DVLEN=$VLEN \
$(clang_env "$2") $2"
      make -C "$APP_DIR" bin/linpack \
        RISCV_CC=clang-18 RISCV_CXX=clang++-18 RISCV_OBJDUMP=llvm-objdump-18 \
        RISCV_AR=llvm-ar-18 RISCV_LD=ld.lld-18 RISCV_STRIP=llvm-strip-18 \
        RISCV_FLAGS="$f" \
        RISCV_LDFLAGS="-nostdlib -fuse-ld=lld $nl/libm.a $lg/libgcc.a \
-Wl,--gc-sections -T$APP_DIR/common/link.ld"
    fi
  else
    [ -n "$GCC_PREFIX" ] || return 1
    local g="$GCC_PREFIX"
    # validated recipe: COMPILER=gcc switches objdump flags; the link template
    # hardcodes $(RUNTIME_LLVM)/$(RISCV_LDFLAGS), so swap in the gcc runtime
    # objects and a gcc-safe link line (-nostdlib: driver adds -lc/-lgloss
    # otherwise, both absent without newlib).
    make -C "$APP_DIR" bin/linpack COMPILER=gcc \
      RISCV_CC="${g}gcc" RISCV_CXX="${g}g++" RISCV_OBJDUMP="${g}objdump" \
      RISCV_AR="${g}ar" RISCV_LD="${g}ld" RISCV_STRIP="${g}strip" \
      RISCV_CC_GCC="${g}gcc" \
      RISCV_FLAGS="$(gcc_flags "$2")" \
      RISCV_CCFLAGS_GCC="$(gcc_flags "$2") -std=gnu99" \
      RUNTIME_LLVM="$GCC_RUNTIME" \
      RISCV_LDFLAGS="$GCC_LDFLAGS"
  fi
}

# ---------------------------------------------------------------- main
STATUS="$OUT/build_status.csv"
echo "tag,compiler,flags,build,run,note" > "$STATUS"

for entry in "${COMBOS[@]}"; do
  IFS='|' read -r tag comp extra <<< "$entry"
  echo ""
  echo "==== $tag ($extra) ===="
  dir="$OUT/$tag"; mkdir -p "$dir"

  if [ "$comp" = clang ] && [ -z "$CLANG_BIN" ]; then
    echo "$tag,$comp,\"$extra\",MISSING,,clang not found" >> "$STATUS"; continue
  fi

  app_clean
  if ! build_one "$comp" "$extra" > "$dir/build.log" 2>&1 \
     || [ ! -f "$APP_DIR/bin/linpack" ]; then
    echo "BUILD FAILED (recorded as result; see $dir/build.log)"
    echo "$tag,$comp,\"$extra\",FAIL,,see build.log" >> "$STATUS"
    continue
  fi
  cp "$APP_DIR/bin/linpack" "$dir/linpack.elf"
  [ -f "$APP_DIR/bin/linpack.dump" ] && cp "$APP_DIR/bin/linpack.dump" "$dir/linpack.dump"

  # direct binary call + +notrace: mock tracer I/O is a major sim-speed tax
  # (see rtl_collect.sh); killed sims lose buffered UART output - run to end
  if ! (cd "$HW_DIR" && ./build/verilator/Vara_tb_verilator +notrace \
        -l "ram,$APP_DIR/bin/linpack,elf") > "$dir/sim.log" 2>&1; then
    echo "SIM FAILED (see $dir/sim.log)"
    echo "$tag,$comp,\"$extra\",OK,FAIL,see sim.log" >> "$STATUS"
    continue
  fi

  grep -E '^(CFG|CHK|CHECK_PHASE|RES|DONE)' "$dir/sim.log" > "$dir/res.csv" || true
  n_res=$(grep -c '^RES,' "$dir/sim.log" || true)
  fails=$(grep -oE 'DONE,fails=[0-9]+' "$dir/sim.log" | grep -oE '[0-9]+' || echo "?")
  echo "$tag,$comp,\"$extra\",OK,OK,res_lines=$n_res func_fails=$fails" >> "$STATUS"
  echo "-- $tag done: $n_res RES rows, functional fails=$fails"
done

# leave the tree in the default (repo clang) state
app_clean
make -C "$APP_DIR" bin/linpack >/dev/null 2>&1 || true

echo ""
echo "== E7 runs complete =="
echo "   status : $STATUS"
python3 "$SCRIPT_DIR/e7_summarize.py" --dir "$OUT" \
  || echo "summarize failed - run e7_summarize.py manually"
