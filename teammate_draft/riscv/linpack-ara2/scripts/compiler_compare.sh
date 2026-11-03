#!/bin/bash
# compiler_compare.sh - dual-compiler evidence table (GCC 13 vs Clang 18).
# Unified disassembly via llvm-objdump-18 (GNU objdump chokes on clang encodings).
set +e
ROOT="/mnt/d/桌面/学校/竞赛/riscv/linpack-ara2"
cd "$ROOT"
LOPT=llvm-objdump-18

count_vec() { # binary symbol -> "total vector instrs"
  $LOPT -d --no-show-raw-insn "$1" | awk -v k="$2" '$0~"<"k">:"{f=1;next} f&&/^$/{exit} f' \
    | grep -cE '	v'
}

echo "function,gcc13_vec_instrs,clang18_vec_instrs" > results/e9_compiler.csv
for FN in dgemm_naive dgemm_blocked dgemm_mr8_m2_p0 dgemm_mr8_m2_p1 dgemm_mr16_m2_p0; do
  G=$(count_vec build/bench $FN)
  C=$(count_vec build/bench_clang $FN)
  echo "$FN,$G,$C" >> results/e9_compiler.csv
done
cat results/e9_compiler.csv

echo "--- vectorizer diagnostics saved ---"
clang-18 --target=riscv64-linux-gnu -march=rv64gcv -mabi=lp64d -O3 -S -o /dev/null \
  -Rpass=loop-vectorize -Rpass-missed=loop-vectorize src/dgemm_naive.c 2>&1 \
  | grep remark > results/diag_clang.txt
riscv64-linux-gnu-gcc -march=rv64gcv -mabi=lp64d -O3 -ffast-math -S -o /dev/null \
  -fopt-info-vec-optimized -fopt-info-vec-missed src/dgemm_naive.c 2>&1 \
  | grep -E "optimized|missed" > results/diag_gcc.txt
echo "clang: $(grep -c 'vectorized loop' results/diag_clang.txt) loops vectorized, $(grep -c missed results/diag_clang.txt) missed"
echo "gcc:   $(grep -c 'optimized: loop vectorized' results/diag_gcc.txt) loops vectorized, $(grep -c missed results/diag_gcc.txt) missed"

echo "--- gcc binary: is dgemm_blocked really scalar? ---"
$LOPT -d --no-show-raw-insn build/bench | awk '/<dgemm_blocked>:/{f=1;next} f&&/^$/{exit} f' | grep -cE '	v' || echo "0 vector instructions (scalar!)"
echo COMPARE_DONE
