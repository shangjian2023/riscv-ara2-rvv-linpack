#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""precision_study.py - 低精度 GEMM 误差-吞吐权衡（Ozaki-lite）。
Ara2 每条 64-bit lane 基于 fpnew：FP64 SIMD x1、FP32 x2、FP16 x4，
故峰值 FLOP/cycle = 2L / 4L / 8L。split2 三遍 fp16 乘加 + fp32 累加，
有效吞吐 = 8L/3 ≈ 1.33x FP64，精度恢复到 fp32 累加级别。"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ara2_model import Ara2Config

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")

FREQ = {2: 1.35, 4: 1.35, 8: 1.35, 16: 1.08}
# 实测精度（tools/fp16_scalar_check.c，x86 宿主标量验证，与 RVV 内核同算法）
MEAS_ERR = {"FP64 (RVV)": 0.0, "FP16 直接": 2.674e-4, "FP16 split2": 3.647e-7}
SIMD = {"FP64 (RVV)": 1, "FP16 直接": 4, "FP16 split2": 4}
PASSES = {"FP64 (RVV)": 1, "FP16 直接": 1, "FP16 split2": 3}

rows = []
for lanes in (2, 4, 8, 16):
    base_peak = 2.0 * lanes * FREQ[lanes]  # FP64 GFLOPS
    for name in ("FP64 (RVV)", "FP16 直接", "FP16 split2"):
        eff = base_peak * SIMD[name] / PASSES[name]
        rows.append([lanes, name, f"{base_peak:.2f}", f"{eff:.2f}",
                     f"{eff/base_peak:.2f}x", f"{MEAS_ERR[name]:.1e}"])
with open(os.path.join(RES, "e10_precision.csv"), "w", newline="",
          encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["lanes", "格式", "FP64峰值GFLOPS", "该格式有效GFLOPS",
                "vs FP64", "归一化误差(实测)"])
    w.writerows(rows)
for r in rows:
    print(r)
print("E10 DONE")
