#!/bin/bash
# Portability: run the SAME riscv64 binary under different qemu VLEN configs.
# RVV-agnostic code (vsetvl everywhere) must produce identical PASS results.
cd "/mnt/d/桌面/学校/竞赛/riscv/linpack-ara2"
for V in 128 256 512 1024; do
  echo "=== qemu VLEN=$V ==="
  qemu-riscv64 -cpu rv64,v=on,vlen=$V,elen=64 ./build/bench \
      > results/bench_vlen$V.csv 2>/dev/null
  echo "checks passed: $(grep -c ',1,0.00e+00' results/bench_vlen$V.csv) / 27"
  echo "linpack rows:"
  grep '^linpack,' results/bench_vlen$V.csv | cut -d, -f2,3,11,12
done
echo PORTABILITY_DONE
