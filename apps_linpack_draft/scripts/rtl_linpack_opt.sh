#!/usr/bin/env bash
# Profile the optimized complete Linpack-style chain. LP_OPT_SCALAR_PHASES
# vectorizes panel/U12 trailing-column updates and makes forward substitution
# row-oriented. Separate output directories preserve all baseline evidence.
#
# WSL usage:
#   ARA_ROOT=/root/work/ara bash rtl_linpack_opt.sh 128
# Optional: LANES=4 NB=32 OUT_ROOT=/root/work/ara/results/local_linpack_opt
set -euo pipefail

N="${1:-128}"
LANES="${LANES:-4}"
NB="${NB:-32}"
ARA_ROOT="${ARA_ROOT:-/root/work/ara}"
OUT_ROOT="${OUT_ROOT:-$ARA_ROOT/results/local_linpack_opt}"
APP_DIR="${APP_DIR:-$ARA_ROOT/apps}"
HW_DIR="$ARA_ROOT/hardware"
MODEL_DIR="${MODEL_DIR:-$HW_DIR/build/verilator}"
MODEL="$MODEL_DIR/Vara_tb_verilator"
MODEL_FLIST="$MODEL_DIR/bender_script_${LANES}_lanes"
XGCC="${RTLC_GCC_PREFIX:-/opt/xpack/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-}"
SHIM="${RTLC_SHIM:-/root/work/shim-include}"
VLEN=$((1024 * LANES))
RUN_DIR="$OUT_ROOT/${LANES}_lanes/n${N}_nb${NB}_opt"

[[ "$N" =~ ^[0-9]+$ ]] && ((N > 0)) || { echo "N must be positive" >&2; exit 2; }
[[ "$NB" =~ ^(32|64)$ ]] || { echo "NB must be 32 or 64" >&2; exit 2; }
[[ -x "$MODEL" ]] || { echo "missing simulator: $MODEL" >&2; exit 2; }
[[ -f "$MODEL_FLIST" ]] || { echo "missing model metadata: $MODEL_FLIST" >&2; exit 2; }
grep -q "^+define+NR_LANES=$LANES$" "$MODEL_FLIST" || {
  echo "model is not built for $LANES lanes" >&2; exit 2;
}
grep -q "^+define+VLEN=$VLEN$" "$MODEL_FLIST" || {
  echo "model is not built for VLEN=$VLEN" >&2; exit 2;
}
[[ ! -e "$RUN_DIR" ]] || { echo "refusing to overwrite $RUN_DIR" >&2; exit 2; }
mkdir -p "$RUN_DIR"

# Preserve the old ELF before replacing the shared apps/bin/linpack target.
if [[ -f "$APP_DIR/bin/linpack" ]]; then
  cp "$APP_DIR/bin/linpack" "$RUN_DIR/previous_linpack.elf"
fi
cp -a "$APP_DIR/linpack" "$RUN_DIR/source"
printf 'N=%s\nNB=%s\nLANES=%s\nVLEN=%s\n' "$N" "$NB" "$LANES" "$VLEN" \
  > "$RUN_DIR/config.txt"
printf 'DGEMM_SWEEP_N=64\nSKIP_CHECK=1\nSKIP_SWEEP=1\nLP_PROFILE=1\nLP_OPT_SCALAR_PHASES=1\n' >> "$RUN_DIR/config.txt"
printf 'chain=blocked_lu+lu_solve+linpack_residual\n' >> "$RUN_DIR/config.txt"
printf 'timing=mcycle around blocked_lu+lu_solve only\n' >> "$RUN_DIR/config.txt"
printf 'note=self-developed Linpack-style workload, not official HPL\n' \
  >> "$RUN_DIR/config.txt"
sha256sum "$MODEL" > "$RUN_DIR/model.sha256"

# Make tracks timestamps, not compiler definitions. Remove only generated app
# objects so no object from another lane/problem-size configuration is reused.
rm -f "$APP_DIR/bin/linpack" "$APP_DIR/bin/linpack.dump" \
      "$APP_DIR/linpack/"*.o "$APP_DIR/linpack/kernel/"*.o \
      "$APP_DIR/common/"*-gcc.o "$APP_DIR/common/"*-llvm.o \
      "$APP_DIR/common/link.ld" "$APP_DIR/linpack/data.S" \
      "$APP_DIR/linpack/data.S.o"
DEFINES="-DSKIP_CHECK=1 -DSKIP_SWEEP=1 -DDGEMM_SWEEP_N=64 -DLINPACK_N=$N -DLINPACK_NB=$NB -DLP_PROFILE=1 -DLP_OPT_SCALAR_PHASES=1"
FLAGS="-O2 -g -mcmodel=medany -march=rv64gcv -mabi=lp64d -ffreestanding -Icommon -I$SHIM -static -fno-common -fno-builtin-printf -ffunction-sections -fdata-sections -DNR_LANES=$LANES -DVLEN=$VLEN $DEFINES"
printf '%s\n' "$FLAGS" > "$RUN_DIR/compiler_flags.txt"

make -C "$APP_DIR" bin/linpack COMPILER=gcc \
  RISCV_CC="${XGCC}gcc" RISCV_CXX="${XGCC}g++" \
  RISCV_OBJDUMP="${XGCC}objdump" RISCV_AR="${XGCC}ar" \
  RISCV_LD="${XGCC}ld" RISCV_STRIP="${XGCC}strip" RISCV_CC_GCC="${XGCC}gcc" \
  RISCV_FLAGS="$FLAGS" RISCV_CCFLAGS_GCC="$FLAGS -std=gnu99" \
  RUNTIME_LLVM="common/crt0-gcc.S.o common/printf-gcc.c.o common/string-gcc.c.o common/serial-gcc.c.o common/util-gcc.c.o" \
  RISCV_LDFLAGS="-static -nostdlib -lm -lgcc -Wl,--gc-sections -T$APP_DIR/common/link.ld" \
  > "$RUN_DIR/build.log" 2>&1

cp "$APP_DIR/bin/linpack" "$RUN_DIR/linpack.elf"
cp "$APP_DIR/bin/linpack.dump" "$RUN_DIR/linpack.dump"
sha256sum "$RUN_DIR/linpack.elf" "$RUN_DIR/linpack.dump" > "$RUN_DIR/binary.sha256"

(
  cd "$HW_DIR"
  "$MODEL" +notrace \
    -l "ram,$RUN_DIR/linpack.elf,elf"
) > "$RUN_DIR/sim.log" 2>&1

grep -E '^(CFG|RES|PROF|DONE)' "$RUN_DIR/sim.log" > "$RUN_DIR/res.csv"
python3 -I - "$RUN_DIR" "$N" "$NB" <<'PY'
import csv
import math
from pathlib import Path
import sys

run = Path(sys.argv[1])
n, nb = int(sys.argv[2]), int(sys.argv[3])
text = (run / "sim.log").read_text(encoding="utf-8", errors="strict")
assert "DONE,fails=0" in text, "missing successful DONE marker"
assert "mode=lp_only" in text, "wrong application mode"
rows = [line for line in text.splitlines() if line.startswith("RES,phase=lp,")]
assert len(rows) == 2, f"expected tuned and baseline rows, got {len(rows)}"
parsed = []
for row in rows:
    fields = dict(field.split("=", 1) for field in row.split(",")[1:])
    assert int(fields["N"]) == n and int(fields["nb"]) == nb
    cycles = int(fields["cycles"])
    residual = float(fields["resid"])
    flops = 2.0 / 3.0 * n**3 + 2.0 * n**2
    assert cycles > 0 and math.isfinite(residual) and 0.0 <= residual < 16.0
    assert math.isclose(float(fields["fpcyc"]), flops / cycles, rel_tol=2e-3)
    parsed.append((fields["mr"], fields["lmul"], cycles, residual, fields["chk"]))
assert parsed[0][:2] == ("8", "2") and parsed[1][:2] == ("4", "1")
profiles = [line for line in text.splitlines() if line.startswith("PROF,")]
assert len(profiles) == 2, f"expected two PROF rows, got {len(profiles)}"
for profile, result in zip(profiles, parsed):
    fields = dict(field.split("=", 1) for field in profile.split(",")[1:])
    assert (int(fields["mr"]), int(fields["lmul"])) == (int(result[0]), int(result[1]))
    assert int(fields["N"]) == n and int(fields["nb"]) == nb
    phases = {name: int(fields[name]) for name in ("panel", "u12", "dgemm", "solve")}
    assert all(value >= 0 for value in phases.values())
    assert sum(phases.values()) <= result[2], "profile sum exceeds timed ROI"
    print("  PROF mr=%s %s" % (result[0], phases))
print(f"VALIDATED N={n} NB={nb}: {len(rows)} complete RTL Linpack rows")
for row in parsed:
    print("  mr=%s lmul=%s cycles=%d residual=%.9f chk=%s" % row)
PY
sha256sum "$RUN_DIR/config.txt" "$RUN_DIR/compiler_flags.txt" \
  "$RUN_DIR/build.log" "$RUN_DIR/sim.log" "$RUN_DIR/res.csv" \
  > "$RUN_DIR/evidence.sha256"
echo "RESULT_DIR=$RUN_DIR"
