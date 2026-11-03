#!/bin/bash
# Build the RVV Linpack benchmark for riscv64 and run it under qemu-user.
# Usage (from WSL):  bash build_and_run.sh [VLEN] [binary-args...]
set -e
ROOT="/mnt/d/桌面/学校/竞赛/riscv/linpack-ara2"
cd "$ROOT"
VLEN="${1:-256}"
shift || true

CROSS=riscv64-linux-gnu-
CC=${CROSS}gcc
mkdir -p build results
$CC -O3 -g -march=rv64gcv -mabi=lp64d -static -fno-math-errno \
    -o build/bench src/bench.c src/dgemm_naive.c src/dgemm_rvv.c src/linpack.c -lm
echo "BUILD_OK ($(file build/bench | cut -d: -f2))"

echo "--- disassembly: vector instruction mix of the mr8_m2 kernel ---"
${CROSS}objdump -d build/bench | awk '/<dgemm_mr8_m2_p0>:/,/^$/' | grep -oE '\tv[a-z0-9.]+' | sort | uniq -c | sort -rn | head -12

echo "--- run under qemu-riscv64 (VLEN=$VLEN) ---"
qemu-riscv64 -cpu rv64,v=on,vlen=$VLEN,elen=64 ./build/bench "$@" | tee results/bench_vlen${VLEN}.csv
echo "RUN_OK"
