#!/bin/bash
# fp16_qemu10.sh - run the FP16 RVV binary on qemu v10 (zvfh support).
cd "/mnt/d/桌面/学校/竞赛/riscv/linpack-ara2"
for V in 128 256 512; do
  echo "--- fp16 RVV @VLEN=$V (qemu v10.0.0, zvfh) ---"
  qemu-riscv64-v10 -cpu rv64,v=on,zfhmin=true,zvfh=true,vlen=$V,elen=64 \
      ./build/fp16_bench 2>&1 | tee results/fp16_vlen$V.csv
done
echo "--- full 27-check bench @VLEN=1024 on qemu v10 ---"
qemu-riscv64-v10 -cpu rv64,v=on,vlen=1024,elen=64 ./build/bench 2>/dev/null \
    > results/bench_qemu10_vlen1024.csv
echo "checks passed: $(grep -c ',1,0.00e+00' results/bench_qemu10_vlen1024.csv) / 27"
echo FP16_QEMU10_DONE
