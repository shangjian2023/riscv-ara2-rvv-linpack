#!/bin/bash
# Build the RVV Linpack benchmark for riscv64 and run it under qemu-user.
# Usage (from WSL):  bash build_and_run.sh [VLEN] [binary-args...]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VLEN="${1:-256}"
shift || true

CROSS=riscv64-linux-gnu-
CC=${CROSS}gcc
PACK_B="${PACK_B:-0}"
PACK_FLAGS=()
case "$PACK_B" in
  0) ;;
  1) PACK_FLAGS=(-DPACK_B=1) ;;
  *) echo "PACK_B must be 0 or 1" >&2; exit 2 ;;
esac
mkdir -p build results
$CC -O3 -g -march=rv64gcv -mabi=lp64d -static -fno-math-errno \
    "${PACK_FLAGS[@]}" \
    -o build/bench src/bench.c src/dgemm_naive.c src/dgemm_rvv.c src/linpack.c -lm
echo "BUILD_OK PACK_B=$PACK_B ($(file build/bench | cut -d: -f2))"

echo "--- disassembly: vector instruction mix of the mr8_m2 kernel ---"
${CROSS}objdump -d build/bench | awk '/<dgemm_mr8_m2_p0>:/,/^$/' | grep -oE '\tv[a-z0-9.]+' | sort | uniq -c | sort -rn | head -12

QEMU="${QEMU:-qemu-riscv64}"
command -v "$QEMU" >/dev/null 2>&1 || {
  echo "MISSING_QEMU: install qemu-user or set QEMU=/path/to/qemu-riscv64" >&2
  exit 127
}
echo "--- run under $QEMU (VLEN=$VLEN) ---"
"$QEMU" -cpu rv64,v=on,vlen="$VLEN",elen=64 ./build/bench "$@" \
  | tee "results/bench_vlen${VLEN}.csv"
echo "RUN_OK"
