#!/bin/bash
# inject_bench.sh - 把静态 bench 二进制注入 K230 Linux 镜像的 rootfs (p2)
set -e
IMG="/mnt/d/桌面/学校/竞赛/riscv/K230 V3.0 开发板客户资料 2024-8-19/1.开发环境/镜像文件/linux开发镜像/CanMV-K230_V3P0_linux_v0.6.4_nncase_v2.9.0.img"
W="/mnt/d/桌面/学校/竞赛/riscv/work"
BENCH="$W/../linpack-ara2/build/bench"

ls -la "$IMG"
[ -f "$BENCH" ] || { echo "bench missing"; exit 1; }

# p2: offset 262144 sectors * 512 = 128MiB, size 256MiB
dd if="$IMG" of="$W/p2.img" bs=1M skip=128 count=256 status=progress
echo "--- rootfs / ---"
debugfs -R "ls -l /" "$W/p2.img" 2>/dev/null | head -12
echo "--- inject ---"
cp "$BENCH" "$W/bench_in"
debugfs -w -R "write $W/bench_in bench" "$W/p2.img" 2>&1 | tail -1
debugfs -w -R "sif /bench mode 0100755" "$W/p2.img" 2>&1 | tail -1
echo "--- verify ---"
debugfs -R "ls -l /bench" "$W/p2.img" 2>/dev/null
echo "--- write back ---"
dd if="$W/p2.img" of="$IMG" bs=1M seek=128 count=256 conv=notrunc status=progress
echo INJECT_DONE
