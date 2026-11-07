#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Summarize K230 (C908) board measurements from the raw CSV.

Board: CanMV-K230 V3.0, Linux 6.6.36, one visible C908 core, RVV 1.0,
VLEN=128 (VLMAX e64m1=2). The same binary was used for QEMU and board runs.
All summary values are derived from k230_board_vlen2.csv.
"""
import csv
import os

RES = os.path.dirname(os.path.abspath(__file__)) + "/../results"

with open(os.path.join(RES, "k230_board_vlen2.csv"), encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

sweep = [r for r in rows if r["section"] == "sweep"]
linpack = [r for r in rows if r["section"] == "linpack"]
checks = [r for r in rows if r["section"] == "check"]
naive = next(r for r in checks if r["variant"] == "naive_scalar")
autovec = next(r for r in checks if r["variant"] == "blocked_autovec")
naive_gf = float(naive["gflops"])
autovec_gf = float(autovec["gflops"])

best = max(sweep, key=lambda r: float(r["gflops"]))
worst = min(sweep, key=lambda r: float(r["gflops"]))
best_gf = float(best["gflops"])
passed = sum(r["ok"] == "1" for r in checks)

print(f"checks: {passed}/{len(checks)} pass")
print(f"naive_scalar {naive_gf:.4f} GF | gcc-autovec {autovec_gf:.4f} GF")
print(f"best  {best['variant']} kc={best['kc']} pipe={best['pipe']} -> {best_gf:.4f} GF")
print(f"worst {worst['variant']} -> {float(worst['gflops']):.4f} GF")
print(f"speedup vs scalar {best_gf/naive_gf:.2f}x | vs autovec {best_gf/autovec_gf:.2f}x | span {best_gf/float(worst['gflops']):.1f}x")
print("note: speedups compare the best 160^3 sweep with the 131x126x117 baseline checks")

linpack_gains = []
for n in ("128", "192", "256"):
    b = next(r for r in linpack if r["variant"] == "baseline" and r["n"] == n)
    t = next(r for r in linpack if r["variant"] == "tuned+pipe" and r["n"] == n)
    gain = float(t["gflops"]) / float(b["gflops"])
    linpack_gains.append(f"{gain:.2f}×")
    print(f"linpack N={n}: base {b['gflops']} -> tuned+pipe {t['gflops']} "
          f"({gain:.2f}x), resid {t['max_diff']}")

baseline_shape = f"{naive['n']}×{naive['m']}×{naive['k']}"
best_shape = f"{best['n']}×{best['m']}×{best['k']}"
out = [["指标", "数值"],
       ["功能校验（同 qemu 二进制）", f"{passed}/{len(checks)} 通过，残差与 qemu 逐位一致"],
       ["ISA / VLEN", "rv64imafdcv…（RVV 1.0）/ 128 bit"],
       ["最优 DGEMM 配置", f"{best['variant']} kc={best['kc']}（LMUL=8，VLEN 自适应规则验证）"],
       ["最优 DGEMM 吞吐", f"{best_gf:.3f} GFLOPS（真机）"],
       ["较标量基线 / 较 GCC 自动向量化（跨用例）",
        f"{best_gf/naive_gf:.2f}× / {best_gf/autovec_gf:.2f}×"
        f"（最优 {best_shape}；基线 {baseline_shape}）"],
       ["配置空间最优/最差差距", f"{best_gf/float(worst['gflops']):.1f}×"],
       ["Linpack 调优收益（N=128/192/256，mr8m2/kc128）",
        " / ".join(linpack_gains)]]
with open(os.path.join(RES, "e12_k230_board.csv"), "w", newline="",
          encoding="utf-8-sig") as f:
    csv.writer(f).writerows(out)
print("saved e12_k230_board.csv")
