#!/bin/bash
# pass_optlevel_test.sh - vector instruction count for base/advised IR at O2/O3.
cd "/mnt/d/桌面/学校/竞赛/riscv/linpack-ara2"
CLANG=clang-18
LOPT=llvm-objdump-18
for OPT in O2 O3; do
  for F in base adj; do
    if [ "$F" = base ]; then SRC=src/dgemm_naive.c; else SRC=build/naive.adj.ll; fi
    $CLANG --target=riscv64-linux-gnu --sysroot=/usr/riscv64-linux-gnu \
        --gcc-toolchain=/usr -march=rv64gcv -mabi=lp64d -c \
        -$OPT -fno-math-errno -fno-inline-functions -g \
        -o /tmp/t_${OPT}_${F}.o "$SRC" 2>/dev/null
    V=$($LOPT -d --no-show-raw-insn /tmp/t_${OPT}_${F}.o | grep -cE '	v')
    # per-function counts
    for FN in dgemm_naive dgemm_blocked; do
      C=$($LOPT -d --no-show-raw-insn /tmp/t_${OPT}_${F}.o \
           | awk -v k=">$FN" '$0~k{f=1;next} /^$/{f=0} f' | grep -cE '	v')
      echo "$OPT $F $FN vec=$C"
    done
    echo "   (module total $OPT $F: $V)"
  done
done
