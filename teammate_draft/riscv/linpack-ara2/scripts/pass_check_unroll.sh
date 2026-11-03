#!/bin/bash
# pass_check_unroll.sh - did the metadata change codegen? Extract each function
# from its "symbol:" line to the next real function symbol (basic-block labels
# like <.LBB0_5> start with a dot and must not terminate the function).
cd "/mnt/d/桌面/学校/竞赛/riscv/linpack-ara2"
for F in base adj; do
  if [ "$F" = base ]; then SRC=src/dgemm_naive.c; else SRC=build/naive.adj.ll; fi
  for OPTL in O2 O3; do
    clang-18 --target=riscv64-linux-gnu --sysroot=/usr/riscv64-linux-gnu \
        --gcc-toolchain=/usr -march=rv64gcv -mabi=lp64d -c \
        -$OPTL -fno-math-errno -g -o /tmp/x_${F}_${OPTL}.o "$SRC" 2>/dev/null
    DUMP=/tmp/dis_${F}_${OPTL}.txt
    llvm-objdump-18 -d --no-show-raw-insn /tmp/x_${F}_${OPTL}.o > "$DUMP"
    for FN in dgemm_naive dgemm_blocked; do
      D=$(awk -v fn="$FN" '
        $0 ~ "^0*[0-9a-f]+ <"fn">:" {f=1; next}
        $0 ~ "^0*[0-9a-f]+ <" && $0 !~ /<\./ {f=0}
        f' "$DUMP")
      L=$(echo "$D" | wc -l)
      VF=$(echo "$D" | grep -c vfmacc)
      VLD=$(echo "$D" | grep -cE 'vl[0-9]?re64|vle64')
      VST=$(echo "$D" | grep -cE 'vs[0-9]?r\.v|vse64')
      echo "$OPTL $F $FN lines=$L vfmacc=$VF vecload=$VLD vecstore=$VST"
    done
  done
done
