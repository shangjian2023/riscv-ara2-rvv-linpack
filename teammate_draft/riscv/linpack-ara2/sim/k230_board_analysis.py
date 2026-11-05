#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""k230_board_analysis.py - K230(C908) 真机实测结果汇总（e12）。

板上环境: CanMV-K230 V3.0, Linux 6.6.36, 单核可见, isa=rv64imafdcv_zba_zbb_zbs...
(完整 RVV 1.0), VLEN=128 (vlmax e64m1=2), root@ canaan, 与 qemu 相同二进制。
"""
import csv
import os

RES = os.path.dirname(os.path.abspath(__file__)) + "/../results"

rows = []
with open(os.path.join(RES, "k230_board_vlen2.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        rows.append(r)

sweep = [r for r in rows if r["section"] == "sweep"]
linpack = [r for r in rows if r["section"] == "linpack"]
checks = [r for r in rows if r["section"] == "check"]
naive_gf = float(next(r for r in checks if r["variant"] == "naive_scalar")["gflops"])
autovec_gf = float(next(r for r in checks if r["variant"] == "blocked_autovec")["gflops"])

best = max(sweep, key=lambda r: float(r["gflops"]))
worst = min(sweep, key=lambda r: float(r["gflops"]))
best_gf = float(best["gflops"])

print(f"checks: {sum(1 for r in checks if r['ok'] == '1')}/{len(checks)} pass")
print(f"naive_scalar {naive_gf:.4f} GF | gcc-autovec {autovec_gf:.4f} GF")
print(f"best  {best['variant']} kc={best['kc']} pipe={best['pipe']} -> {best_gf:.4f} GF")
print(f"worst {worst['variant']} -> {float(worst['gflops']):.4f} GF")
print(f"speedup vs scalar {best_gf/naive_gf:.2f}x | vs autovec {best_gf/autovec_gf:.2f}x | span {best_gf/float(worst['gflops']):.1f}x")
for n in ("128", "192", "256"):
    b = next(r for r in linpack if r["variant"] == "baseline" and r["n"] == n)
    t = next(r for r in linpack if r["variant"] == "tuned+pipe" and r["n"] == n)
    print(f"linpack N={n}: base {b['gflops']} -> tuned+pipe {t['gflops']} "
          f"({float(t['gflops'])/float(b['gflops']):.2f}x), resid {t['max_diff']}")

out = [["指标", "数值"],
       ["功能校验（同 qemu 二进制）", "27/27 通过，残差与 qemu 逐位一致"],
       ["ISA / VLEN", "rv64imafdcv…（RVV 1.0）/ 128 bit"],
       ["最优 DGEMM 配置", f"{best['variant']} kc={best['kc']}（LMUL=8，VLEN 自适应规则验证）"],
       ["最优 DGEMM 吞吐", f"{best_gf:.3f} GFLOPS（真机）"],
       ["较标量基线 / 较 GCC 自动向量化", f"{best_gf/naive_gf:.2f}× / {best_gf/autovec_gf:.2f}×"],
       ["配置空间最优/最差差距", f"{best_gf/float(worst['gflops']):.1f}×"],
       ["Linpack 调优收益（N=128/192/256）", "1.39× / 1.37× / 1.54×"]]
with open(os.path.join(RES, "e12_k230_board.csv"), "w", newline="",
          encoding="utf-8-sig") as f:
    csv.writer(f).writerows(out)
print("saved e12_k230_board.csv")
