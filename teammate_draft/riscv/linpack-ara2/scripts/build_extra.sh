#!/bin/bash
# build_extra.sh - incremental study builds:
#   1) instrumented kernel (-DINSTR_COUNT) dynamic instruction counters
#   2) low-precision FP16 kernels (needs Zfh)
#   3) clang-18 cross build (dual-compiler comparison)
set +e
ROOT="/mnt/d/桌面/学校/竞赛/riscv/linpack-ara2"
cd "$ROOT"
GCC=riscv64-linux-gnu-gcc
CLANG=clang-18

echo "=== [1] instrumented build ==="
$GCC -O3 -g -march=rv64gcv -mabi=lp64d -static -fno-math-errno -DINSTR_COUNT \
    -o build/instr_bench src/instr_bench.c src/dgemm_naive.c src/dgemm_rvv.c -lm \
    && echo INSTR_BUILD_OK
for V in 256 512; do
  echo "--- instr counters @VLEN=$V ---"
  qemu-riscv64 -cpu rv64,v=on,vlen=$V,elen=64 ./build/instr_bench \
      | tee results/instr_vlen$V.csv
done

echo "=== [2] fp16 build (Zfh) ==="
$GCC -O3 -g -march=rv64gcv_zfh -mabi=lp64d -static -fno-math-errno \
    -o build/fp16_bench src/fp16_bench.c src/dgemm_naive.c src/dgemm_rvv.c src/dgemm_fp16.c -lm \
    && echo FP16_BUILD_OK
for V in 256 512; do
  echo "--- fp16 @VLEN=$V (qemu zfh=true) ---"
  qemu-riscv64 -cpu rv64,v=on,zfh=true,vlen=$V,elen=64 ./build/fp16_bench \
      | tee results/fp16_vlen$V.csv
done

echo "=== [3] clang-18 cross build ==="
# Ubuntu cross sysroot via gcc-toolchain; try link with lld and gnu ld
$CLANG --target=riscv64-linux-gnu --sysroot=/usr/riscv64-linux-gnu \
    --gcc-toolchain=/usr -march=rv64gcv -mabi=lp64d -static -O3 -g -fno-math-errno \
    -o build/bench_clang src/bench.c src/dgemm_naive.c src/dgemm_rvv.c src/linpack.c -lm \
    && echo CLANG_BUILD_OK
if [ -f build/bench_clang ]; then
  echo "--- clang binary under qemu VLEN=512 (functional) ---"
  qemu-riscv64 -cpu rv64,v=on,vlen=512,elen=64 ./build/bench_clang > results/bench_clang_vlen512.csv 2>/dev/null
  echo "clang checks passed: $(grep -c ',1,0.00e+00' results/bench_clang_vlen512.csv) / 27"
  grep '^linpack,' results/bench_clang_vlen512.csv | cut -d, -f2,3,11 | head -9
  echo "--- clang vs gcc vector code for the blocked (autovec) kernel ---"
  for B in build/bench build/bench_clang; do
    echo "[$B]"
    riscv64-linux-gnu-objdump -d $B | awk '/<dgemm_blocked>:/{f=1;next} f&&/^$/{exit} f' \
      | grep -oE '\sv[a-z0-9.]+' | sort | uniq -c | sort -rn | head -6
    riscv64-linux-gnu-objdump -d $B | awk '/<dgemm_mr8_m2_p0>:/{f=1;next} f&&/^$/{exit} f' \
      | grep -oE '\sv[a-z0-9.]+' | sort | uniq -c | sort -rn | head -6
  done
fi
echo EXTRA_DONE
