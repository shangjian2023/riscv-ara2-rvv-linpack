#!/bin/bash
# llvm_pass_flow.sh - full flow of the Ara2VecAdvisor LLVM NewPM pass:
#   plugin build -> IR emit (-O1, loops intact, not yet vectorized)
#   -> opt pass (metadata injection) -> clang -O2 codegen (unroll honors MD)
#   -> static instruction-mix comparison -> qemu functional check.
set +e
ROOT="/mnt/d/桌面/学校/竞赛/riscv/linpack-ara2"
cd "$ROOT"
CLANG=clang-18
OPT=opt-18
LOPT=llvm-objdump-18
CXX=clang++-18

echo "=== [1] build pass plugin ==="
$CXX -fPIC -shared -std=gnu++20 -O2 \
    $(llvm-config-18 --cxxflags | sed 's/-std=[^ ]*//g') \
    llvm-pass/Ara2VecAdvisor.cpp -o build/libAra2Advisor.so \
    $(llvm-config-18 --ldflags --libs core passes analysis support) 2>&1 | grep -E "error" | head -5
ls -la build/libAra2Advisor.so 2>/dev/null && echo PLUGIN_OK || exit 1

echo "=== [2] emit pre-vectorization IR (-O1 -g) ==="
$CLANG --target=riscv64-linux-gnu -march=rv64gcv -mabi=lp64d -O1 -g \
    -emit-llvm -S src/dgemm_naive.c -o build/naive.ll && echo IR_OK

echo "=== [3] run ara2-advisor ==="
$OPT -load-pass-plugin=build/libAra2Advisor.so \
     -passes='function(ara2-advisor)' -S build/naive.ll -o build/naive.adj.ll
grep -c 'llvm.loop.unroll.count' build/naive.adj.ll

echo "=== [4] codegen: baseline vs advised ==="
MAIN=tools/pass_demo_main.c
NOINLINE="-fno-inline-functions"
$CLANG --target=riscv64-linux-gnu --sysroot=/usr/riscv64-linux-gnu --gcc-toolchain=/usr \
    -march=rv64gcv -mabi=lp64d -static -O2 -fno-math-errno -g $NOINLINE \
    -o build/pass_demo_base $MAIN src/dgemm_naive.c -lm && echo BASE_OK
$CLANG --target=riscv64-linux-gnu --sysroot=/usr/riscv64-linux-gnu --gcc-toolchain=/usr \
    -march=rv64gcv -mabi=lp64d -static -O2 -fno-math-errno -g $NOINLINE \
    -o build/pass_demo_adj $MAIN build/naive.adj.ll -lm && echo ADJ_OK

echo "=== [5] static vector-mix comparison ==="
echo "binary,function,vfmacc,vfmul_v,vec_load,vec_store,fma_per_memvec" > results/e11_llvm_pass.csv
for FN in dgemm_naive dgemm_blocked; do
  for PAIR in "base:build/pass_demo_base" "advised:build/pass_demo_adj"; do
    TAG=${PAIR%%:*}; BIN=${PAIR#*:}
    SEC=$($LOPT -d --no-show-raw-insn "$BIN" | awk -v fn="$FN" '
      $0 ~ "^0*[0-9a-f]+ <"fn">:" {f=1; next}
      $0 ~ "^0*[0-9a-f]+ <" && $0 !~ /<\./ {f=0}
      f')
    F=$(echo "$SEC" | grep -c 'vfmacc')
    M=$(echo "$SEC" | grep -c 'vfmul\.vv')
    LD=$(echo "$SEC" | grep -cE 'vl[0-9]?re64|vle64')
    ST=$(echo "$SEC" | grep -cE 'vs[0-9]?r\.v|vse64')
    MEM=$((LD + ST))
    if [ "$MEM" -gt 0 ]; then
      RAT=$(awk "BEGIN{printf \"%.2f\", ($F+$M)/$MEM}")
    else
      RAT="na"
    fi
    echo "$TAG,$FN,$F,$M,$LD,$ST,$RAT" >> results/e11_llvm_pass.csv
  done
done
cat results/e11_llvm_pass.csv

echo "=== [6] qemu functional check of the advised binary ==="
qemu-riscv64 -cpu rv64,v=on,vlen=512,elen=64 ./build/pass_demo_adj 2>/dev/null | tail -3
echo PASS_FLOW_DONE
