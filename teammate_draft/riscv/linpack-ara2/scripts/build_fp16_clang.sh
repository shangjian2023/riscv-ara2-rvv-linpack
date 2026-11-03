#!/bin/bash
# build_fp16_clang.sh - FP16 kernels via clang (GCC 13 lacks f16 RVV intrinsics),
# plus clang vectorization diagnostics and dual-compiler code comparison.
set +e
ROOT="/mnt/d/桌面/学校/竞赛/riscv/linpack-ara2"
cd "$ROOT"
CLANG=clang-18
LOPT=llvm-objdump-18

echo "=== [A] clang fp16 build (zvfh) ==="
$CLANG --target=riscv64-linux-gnu --sysroot=/usr/riscv64-linux-gnu \
    --gcc-toolchain=/usr -march=rv64gcv_zvfh -mabi=lp64d -static -O3 -g -fno-math-errno \
    -o build/fp16_bench src/fp16_bench.c src/dgemm_naive.c src/dgemm_rvv.c src/dgemm_fp16.c -lm \
    && echo FP16_CLANG_BUILD_OK
for V in 256 512; do
  echo "--- fp16 @VLEN=$V ---"
  qemu-riscv64 -cpu rv64,v=on,zfh=true,zvfh=true,vlen=$V,elen=64 ./build/fp16_bench \
      2>/dev/null | tee results/fp16_vlen$V.csv
done

echo "=== [B] compiler vectorizer diagnostics ==="
echo "--- clang-18 -Rpass on dgemm_naive.c ---"
$CLANG --target=riscv64-linux-gnu -march=rv64gcv -mabi=lp64d -O3 -S -o /dev/null \
    -Rpass=loop-vectorize -Rpass-missed=loop-vectorize -Rpass-analysis=loop-vectorize \
    src/dgemm_naive.c 2>&1 | grep -E "remark:" | head -12
echo "--- gcc-13 -fopt-info-vec on the same file (same flags) ---"
riscv64-linux-gnu-gcc -march=rv64gcv -mabi=lp64d -O3 -ffast-math -S -o /dev/null \
    -fopt-info-vec-optimized -fopt-info-vec-missed src/dgemm_naive.c 2>&1 | head -12

echo "=== [C] dual-compiler kernel code comparison (llvm-objdump for clang) ==="
echo "columns: gcc_vs_clang for dgemm_blocked (autovec) and dgemm_mr8_m2_p0"
for MODE in dgemm_blocked dgemm_mr8_m2_p0; do
  echo "--- $MODE ---"
  echo "[gcc-13]"
  riscv64-linux-gnu-objdump -d build/bench | awk -v k="$MODE" '$0~"<"k">:"{f=1;next} f&&/^$/{exit} f' \
    | grep -oE '	v[a-z0-9.]+' | sort | uniq -c | sort -rn | head -5
  echo "[clang-18]"
  $LOPT -d --no-show-raw-insn build/bench_clang | awk -v k="$MODE" '$0~"<"k">:"{f=1;next} f&&/^$/{exit} f' \
    | grep -oE '	v[a-z0-9.]+' | sort | uniq -c | sort -rn | head -5
done
echo "=== [D] clang disasm of fp16 core kernel (evidence of vfwmacc) ==="
$LOPT -d --no-show-raw-insn build/fp16_bench | awk '/<gemm_f16_core>:/{f=1;next} f&&/^$/{exit} f' \
  | grep -oE '	v[a-z0-9.]+' | sort | uniq -c | sort -rn | head -8
echo FP16_CLANG_DONE
