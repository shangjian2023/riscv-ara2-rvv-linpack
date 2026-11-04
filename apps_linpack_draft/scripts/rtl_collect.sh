#!/usr/bin/env bash
# rtl_collect.sh - Experiments E0 + E1: RTL data collection (Ara2 / Verilator).
#
# E0 (paper anchor): run the official fmatmul app at the two Ara2-paper anchor
# sizes 32^3 (76%) and 64^3 (94%). With generated data.S the app runs exactly
# one size (s == M) and always verifies, so each anchor = one build + one run.
# E1 (variant comparison): run the linpack app in its default mode
# (v0/v2 + 6 anchor kernels + linpack chain, functional check on).
#
# Per config (default "4_lanes 16_lanes"): (RE)VERILATE for the config (the
# config .mk is a make dependency of the model - without this step a config
# switch would silently reuse the previous model!), (re)build apps, run both
# on the verilated model, archive logs, emit CSVs.
#
# Usage (WSL, toolchains installed):
#   cd <ara>/apps && bash <path-to>/rtl_collect.sh
#   RTLC_CONFIGS="2_lanes 4_lanes 8_lanes 16_lanes" bash <path>/rtl_collect.sh
#   RTLC_FMATMUL_ARGS="64 64 64" bash <path>/rtl_collect.sh   # one anchor only
#   RTLC_LINPACK_DEFINES="-DFULL_SWEEP=1" bash <path>/rtl_collect.sh
#
# Env:
#   ARA_ROOT           default: auto (run from <ara> or <ara>/apps)
#   RTLC_CONFIGS       default: "4_lanes 16_lanes"
#   RTLC_FMATMUL_ARGS  default: "32 32 32|64 64 64"  ('|'-separated M N P triples)
#   RTLC_OUT           default: <ara>/results/rtl
#   RTLC_LINPACK_DEFINES  extra ENV_DEFINES for the linpack app build
#   E8_MODEL           path to ara2_model.py for the final comparison
#
# Outputs:
#   $RTLC_OUT/<config>/fmatmul.log, fmatmul.csv, linpack.log, res.csv
#   $RTLC_OUT/rtl_all.csv           (merged, with config/lanes columns)
#   E0 anchor comparison lives in e8_compare.py (paper constants there).
set -uo pipefail

# ---------------------------------------------------------------- locate ara
if [ -n "${ARA_ROOT:-}" ]; then
  :
elif [ -d "$(pwd)/hardware" ] && [ -d "$(pwd)/apps" ]; then
  ARA_ROOT="$(pwd)"
elif [ -d "$(pwd)/../hardware" ] && [ -d "$(pwd)/../apps" ]; then
  ARA_ROOT="$(cd .. && pwd)"
else
  echo "error: run from <ara>/ or <ara>/apps/, or set ARA_ROOT" >&2
  exit 1
fi
APP_DIR="$ARA_ROOT/apps"
HW_DIR="$ARA_ROOT/hardware"
OUT="${RTLC_OUT:-$ARA_ROOT/results/rtl}"
CONFIGS="${RTLC_CONFIGS:-4_lanes 16_lanes}"
FMAT_TRIPLES="${RTLC_FMATMUL_ARGS:-32 32 32|64 64 64}"
LP_DEFINES="${RTLC_LINPACK_DEFINES:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$OUT"

# ---------------- compiler selection --------------------------------------
# RTLC_COMPILER=clang|gcc|auto. auto: repo-built clang if installed, else the
# validated apt/xPack GCC recipe (see apps_linpack_draft/scripts/e7_run.sh -
# the app link template hardcodes $(RUNTIME_LLVM)/$(RISCV_LDFLAGS), both of
# which must be swapped for gcc builds; -nostdlib because the driver adds
# -lc/-lgloss that don't exist without newlib).
RTLC_COMPILER="${RTLC_COMPILER:-auto}"
if [ "$RTLC_COMPILER" = auto ]; then
  if [ -x "$ARA_ROOT/install/riscv-llvm/bin/clang" ]; then
    RTLC_COMPILER=clang
  else
    RTLC_COMPILER=gcc
  fi
fi
GCC_PREFIX=""
if [ "$RTLC_COMPILER" = gcc ]; then
  for p in "${RTLC_GCC_PREFIX:-}" \
           "$ARA_ROOT/install/riscv-gcc/bin/riscv64-unknown-elf-" \
           "/opt/xpack/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-" \
           "riscv64-unknown-elf-" "riscv64-linux-gnu-"; do
    [ -n "$p" ] || continue
    if command -v "${p}gcc" >/dev/null 2>&1; then GCC_PREFIX="$p"; break; fi
  done
  [ -n "$GCC_PREFIX" ] || { echo "error: no riscv gcc found" >&2; exit 1; }
fi
SHIM="${RTLC_SHIM:-/root/work/shim-include}"
GCC_RUNTIME="common/crt0-gcc.S.o common/printf-gcc.c.o common/string-gcc.c.o common/serial-gcc.c.o common/util-gcc.c.o"

rtl_gcc_flags() { # $1 = extra defines
  # -O2 is REQUIRED, not cosmetic: at -O0 gcc does not inline runtime.h's
  # plain-inline start_timer/stop_timer/get_timer -> undefined refs at link.
  echo "-O2 -g -mcmodel=medany -march=rv64gcv -mabi=lp64d -ffreestanding -Icommon -I$SHIM \
-static -fno-common -fno-builtin-printf -ffunction-sections -fdata-sections \
-DNR_LANES=$LANES -DVLEN=$VLEN $1"
}

# build_app <app> <defines> [extra make args...]
build_app() {
  local app="$1" defs="$2"; shift 2
  # Clean first: make compares timestamps only, not flags - objects from a
  # previous config/defines set would be silently relinked into this build
  # (e.g. -DNR_LANES=4 objects inside a 16_lanes binary => mislabeled data).
  rm -f "$APP_DIR/bin/$app"
  find "$APP_DIR/$app" -name '*.o' -delete 2>/dev/null || true
  rm -f "$APP_DIR/common/"*-gcc.o "$APP_DIR/common/"*-llvm.o \
        "$APP_DIR/common/link.ld" \
        "$APP_DIR/$app/data.S" "$APP_DIR/$app/data.S.o" 2>/dev/null || true
  if [ "$RTLC_COMPILER" = clang ]; then
    make -C "$APP_DIR" "bin/$app" ENV_DEFINES="$defs" "$@"
  else
    make -C "$APP_DIR" "bin/$app" COMPILER=gcc \
      RISCV_CC="${GCC_PREFIX}gcc" RISCV_CXX="${GCC_PREFIX}g++" \
      RISCV_OBJDUMP="${GCC_PREFIX}objdump" RISCV_AR="${GCC_PREFIX}ar" \
      RISCV_LD="${GCC_PREFIX}ld" RISCV_STRIP="${GCC_PREFIX}strip" \
      RISCV_CC_GCC="${GCC_PREFIX}gcc" \
      RISCV_FLAGS="$(rtl_gcc_flags "$defs")" \
      RISCV_CCFLAGS_GCC="$(rtl_gcc_flags "$defs") -std=gnu99" \
      RUNTIME_LLVM="$GCC_RUNTIME" \
      RISCV_LDFLAGS="-static -nostdlib -lm -lgcc -Wl,--gc-sections -T$APP_DIR/common/link.ld" \
      "$@"
  fi
}

echo "== RTL collection =="
echo "   ara root : $ARA_ROOT"
echo "   configs  : $CONFIGS"
echo "   compiler : $RTLC_COMPILER${GCC_PREFIX:+ ($GCC_PREFIX...)}"
echo "   fmatmul  : $FMAT_TRIPLES (E0 paper anchors)"
echo "   out      : $OUT"

run_sim() { # $1=app $2=config $3=logfile
  # Call the verilated binary directly (same command as `make simv`) so we can
  # pass +notrace: the CVA6 mock tracer writes EVERY committed instruction to
  # trace_hart_0.dasm (~40MB/run, big sim-speed tax). Requires the local
  # cva6.sv plusarg patch; unpatched models ignore the plusarg safely.
  # NOTE: never SIGKILL the sim - Verilator buffers SV $write output (UART
  # prints are lost if the process is killed before $finish; SIGINT stops
  # gracefully via VerilatorSimCtrl).
  (cd "$HW_DIR" && ./build/verilator/Vara_tb_verilator +notrace \
     -l "ram,$APP_DIR/bin/$1,elf") > "$3" 2>&1
}

: > "$OUT/rtl_all.csv"
echo "config,lanes,app,s,N,cycles,fpcyc,util,verified" >> "$OUT/rtl_all.csv"

for CFG in $CONFIGS; do
  LANES="${CFG%_lanes}"; LANES="${LANES##*/}"
  VLEN=$((1024 * LANES))
  echo ""
  echo "==== config $CFG (L=$LANES VLEN=$VLEN) ===="
  dir="$OUT/$CFG"; mkdir -p "$dir"

  # ---------------- (re)verilate for this config ---------------------------
  # The model binary carries NR_LANES baked in. The make target only compares
  # timestamps against config/<cfg>.mk, so switching configs does NOT trigger
  # a rebuild by itself (stale binary looks "up to date"). Force it by
  # touching the config file - but only when the stamp says another config
  # was built last (avoids pointless 10-min re-verilations on re-runs).
  STAMP="$HW_DIR/build/verilator/.ara_verilate_stamp"
  if [ "$(cat "$STAMP" 2>/dev/null || true)" = "$CFG" ] \
     && [ -x "$HW_DIR/build/verilator/Vara_tb_verilator" ]; then
    echo "[V] model already verilated for $CFG - skip"
  else
    echo "[V] verilate config=$CFG (full rebuild, ~10-15 min) ..."
    touch "$ARA_ROOT/config/$CFG.mk"
    if ! make -C "$HW_DIR" verilate config="$CFG" \
         > "$dir/verilate.log" 2>&1; then
      echo "  VERILATE FAILED for $CFG (see $dir/verilate.log) - SKIPPING config"
      continue
    fi
    echo "$CFG" > "$STAMP"
  fi

  # ---------------- E0: fmatmul (official app, anchor sizes) --------------
  # '|'-separated triples -> newline-separated: a plain `read -r TRIPLE` then
  # sees each triple on its own line (with a 2-var read the second field would
  # be swallowed by REST and never visited - that bug cost us the 64^3 anchor).
  while IFS= read -r TRIPLE; do
    [ -n "$TRIPLE" ] || continue
    ANCHOR="$(echo "$TRIPLE" | awk '{print $1}')"
    echo "[E0] building fmatmul ($TRIPLE) ..."
    if ! build_app fmatmul "" def_args_fmatmul="\"$TRIPLE\"" \
         > "$dir/fmatmul_build_$ANCHOR.log" 2>&1; then
      echo "  fmatmul/$ANCHOR BUILD FAILED (see $dir/fmatmul_build_$ANCHOR.log)"
      continue
    fi
    echo "[E0] running fmatmul $ANCHOR on RTL ..."
    if run_sim fmatmul "$CFG" "$dir/fmatmul_$ANCHOR.log"; then
      python3 - "$dir/fmatmul_$ANCHOR.log" "$CFG" "$LANES" "$OUT/rtl_all.csv" <<'PY'
import re, sys
log, cfg, lanes, allcsv = sys.argv[1:5]
rows = []
s = None
for line in open(log, encoding="utf-8", errors="ignore"):
    m = re.search(r"Calculating a \((\d+) x (\d+)\) x \((\d+) x (\d+)\)", line)
    if m:
        s = int(m.group(1))
        continue
    m = re.search(r"execution took (\d+) cycles", line)
    if m and s is not None:
        rows.append([s, m.group(1), None, None]); continue
    m = re.search(r"performance is ([\d.]+) FLOP/cycle \(([\d.]+)%", line)
    if m and rows and rows[-1][2] is None:
        rows[-1][2], rows[-1][3] = m.group(1), m.group(2)
    if "Passed." in line and rows:
        rows[-1].append("yes")
with open(allcsv, "a", encoding="utf-8") as f:
    for r in rows:
        if len(r) >= 4:
            f.write(f"{cfg},{lanes},fmatmul,{r[0]},{r[0]},{r[1]},{r[2]},{r[3]},"
                    f"{r[4] if len(r) > 4 else '?'}\n")
print(f"  fmatmul: {len(rows)} sizes parsed")
PY
    else
      echo "  fmatmul/$ANCHOR SIM FAILED (see $dir/fmatmul_$ANCHOR.log)"
    fi
  done <<< "$(printf '%s\n' "$FMAT_TRIPLES" | tr '|' '\n')"

  # ---------------- E1: linpack app (default mode) -------------------------
  echo "[E1] building linpack ..."
  if ! build_app linpack "$LP_DEFINES" \
       > "$dir/linpack_build.log" 2>&1; then
    echo "  linpack BUILD FAILED (see $dir/linpack_build.log) - continuing"
  else
    echo "[E1] running linpack on RTL ..."
    if run_sim linpack "$CFG" "$dir/linpack.log"; then
      grep -E '^(CFG|CHK|CHECK_PHASE|RES|DONE)' "$dir/linpack.log" \
        > "$dir/res.csv" || true
      n=$(grep -c '^RES,' "$dir/linpack.log" || true)
      fails=$(grep -oE 'DONE,fails=[0-9]+' "$dir/linpack.log" \
              | grep -oE '[0-9]+' || echo "?")
      echo "  linpack: $n RES rows, functional fails=$fails"
    else
      echo "  linpack SIM FAILED (see $dir/linpack.log)"
    fi
  fi
done

echo ""
echo "== collection done =="
echo "   merged csv : $OUT/rtl_all.csv"
echo "   next       : python3 $SCRIPT_DIR/e8_compare.py --rtl-dir $OUT [--model <path>/ara2_model.py]"
python3 "$SCRIPT_DIR/e8_compare.py" --rtl-dir "$OUT" ${E8_MODEL:+--model "$E8_MODEL"} || \
  echo "e8 comparison failed - run e8_compare.py manually"
