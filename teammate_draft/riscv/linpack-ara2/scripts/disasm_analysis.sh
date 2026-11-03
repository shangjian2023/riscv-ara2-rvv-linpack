#!/bin/bash
# Static instruction-mix analysis of the generated micro-kernels: count vector
# instructions and detect stack spills (loads/stores through sp) per kernel.
set +e
ROOT="/mnt/d/桌面/学校/竞赛/riscv/linpack-ara2"
cd "$ROOT"
OBJ=build/bench
DIS=$(mktemp)
riscv64-linux-gnu-objdump -d "$OBJ" > "$DIS"
echo "kernel,v_instr,vfmacc,vle64,vse64,vmv,vsetvl,other_v,sp_ldst,total"
for K in dgemm_mr2_m1_p0 dgemm_mr2_m1_p1 dgemm_mr2_m4_p1 dgemm_mr4_m2_p0 \
         dgemm_mr4_m2_p1 dgemm_mr8_m1_p0 dgemm_mr8_m1_p1 dgemm_mr8_m2_p0 \
         dgemm_mr8_m2_p1 dgemm_mr8_m4_p0 dgemm_mr8_m4_p1 dgemm_mr16_m2_p0 \
         dgemm_mr16_m2_p1 dgemm_mr4_m8_p0 dgemm_mr2_m8_p1; do
  SEC=$(awk -v k="$K" '$0 ~ "<"k">:" {f=1; next} f && /^$/ {exit} f {print}' "$DIS")
  V=$(echo "$SEC" | grep -cE '	v')
  F=$(echo "$SEC" | grep -c 'vfmacc')
  L=$(echo "$SEC" | grep -c 'vle64')
  S=$(echo "$SEC" | grep -c 'vse64')
  M=$(echo "$SEC" | grep -c '	vmv')
  T=$(echo "$SEC" | grep -c 'vsetvl')
  O=$((V - F - L - S - M - T))
  SP=$(echo "$SEC" | grep -cE '(fld|fsd|ld|sd)	[a-z0-9]+,-?[0-9]*\(sp\)')
  TOT=$(echo "$SEC" | grep -cE '^ +[0-9a-f]+:')
  echo "$K,$V,$F,$L,$S,$M,$T,$O,$SP,$TOT"
done
echo "--- vector instructions of dgemm_mr2_m1_p1 (first 40) ---"
awk '/<dgemm_mr2_m1_p1>:/{f=1;next} f&&/^$/{exit} f' "$DIS" | grep -E '	v' | head -40
rm -f "$DIS"
