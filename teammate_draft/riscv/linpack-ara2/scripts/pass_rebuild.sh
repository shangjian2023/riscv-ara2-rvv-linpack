#!/bin/bash
# pass_rebuild.sh - rebuild the plugin, rerun on IR, verify metadata rewrite.
cd "/mnt/d/桌面/学校/竞赛/riscv/linpack-ara2"
set -e
echo "--- build ---"
clang++-18 -fPIC -shared -std=gnu++20 -O2 \
    $(llvm-config-18 --cxxflags | sed 's/-std=[^ ]*//g') \
    llvm-pass/Ara2VecAdvisor.cpp -o build/libAra2Advisor.so \
    $(llvm-config-18 --ldflags --libs core passes analysis support)
echo BUILD_OK
echo "--- emit IR (-O1) ---"
clang-18 --target=riscv64-linux-gnu -march=rv64gcv -mabi=lp64d -O1 -g \
    -emit-llvm -S src/dgemm_naive.c -o build/naive.ll 2>/dev/null
echo "--- run advisor ---"
opt-18 -load-pass-plugin=build/libAra2Advisor.so \
     -passes='function(ara2-advisor)' -S build/naive.ll -o build/naive.adj.ll 2>&1 | grep ARA2
echo "--- metadata check: any loop ID still containing unroll.disable? ---"
BAD=$(grep -n 'unroll.disable' build/naive.adj.ll || true)
echo "${BAD:-none}"
echo "--- distinct loop IDs with our keys ---"
grep -n 'unroll_and_jam.count\|unroll.count' build/naive.adj.ll | head -5
