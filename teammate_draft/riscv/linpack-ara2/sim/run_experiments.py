#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_experiments.py - 实验矩阵驱动：生成全部 CSV 结果表。"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ara2_model import Ara2Config, KernelParams, model_rvv_dgemm, model_autovec_gemm, \
    model_scalar_gemm, model_multicore, model_linpack

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
os.makedirs(ROOT, exist_ok=True)


def w(name, header, rows):
    p = os.path.join(ROOT, name)
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow(header)
        csv.writer(f).writerows(rows)
    print(f"[csv] {name}: {len(rows)} rows")


# 频率随 lane 数（论文 TT 工艺角: 2/4/8->1.35GHz, 16->1.08GHz）
FREQ = {2: 1.35, 4: 1.35, 8: 1.35, 16: 1.08}

# ---------------- E1: 优化变体对比 (N=256, L=16) ----------------
def e1_variants():
    rows = []
    mc = Ara2Config(lanes=16, freq_ghz=FREQ[16])
    n = m = k = 256
    r = model_scalar_gemm(n, m, k, mc)
    rows.append(["v0_scalar", n, "0", "0", "0", "0", f"{r.gflops:.3f}",
                 f"{r.peak_gflops:.2f}", f"{r.utilization*100:.1f}", "scalar"])
    r = model_autovec_gemm(n, m, k, mc)
    rows.append(["v2_autovec", n, "0", "0", "0", "0", f"{r.gflops:.3f}",
                 f"{r.peak_gflops:.2f}", f"{r.utilization*100:.1f}",
                 r.breakdown["bound"]])
    cfgs = [
        ("v3_rvv_mr4_m1_kc64", KernelParams(mr=4, lmul=1, kc=64, k_unroll=2)),
        ("v4_rvv_mr8_m2_kc128", KernelParams(mr=8, lmul=2, kc=128, k_unroll=2)),
        ("v4_rvv_mr8_m2_kc256", KernelParams(mr=8, lmul=2, kc=256, k_unroll=2)),
        ("v5_pipe_mr8_m2_kc128", KernelParams(mr=8, lmul=2, kc=128, pipe=1, k_unroll=1)),
        ("v4_rvv_mr16_m2_kc128(溢出)", KernelParams(mr=16, lmul=2, kc=128, k_unroll=2)),
        ("v4_rvv_mr8_m4_kc128(溢出)", KernelParams(mr=8, lmul=4, kc=128, k_unroll=2)),
    ]
    base = None
    for name, kp in cfgs:
        r = model_rvv_dgemm(n, m, k, kp, mc)
        if base is None:
            base = r.gflops
        b = r.breakdown
        rows.append([name, n, kp.mr, kp.lmul, kp.kc, kp.pipe, f"{r.gflops:.3f}",
                     f"{r.peak_gflops:.2f}", f"{r.utilization*100:.1f}",
                     b["bound"], b["vregs"], "YES" if b["vregs_overflow"] else "no",
                     f"{r.gflops/base:.2f}x",
                     f"{b['issue']:.1f}", f"{b['fpu']:.1f}", f"{b['vlsu']:.1f}",
                     f"{b['issue']/b['fpu']*100:.0f}"])
    w("e1_variants.csv",
      ["variant", "N", "MR", "LMUL", "KC", "PIPE", "GFLOPS", "peak", "util%",
       "bound", "vregs", "VRF溢出", "vs_v3", "issue_cyc/k", "fpu_cyc/k", "vlsu_cyc/k",
       "发射占用率%"],
      rows)


# ---------------- E2: lane 扩展性 ----------------
def e2_lanes():
    rows = []
    for n in (256, 1024):
        for lanes in (2, 4, 8, 16):
            mc = Ara2Config(lanes=lanes, freq_ghz=FREQ[lanes])
            for name, kp in [("v4", KernelParams(mr=8, lmul=2, kc=128)),
                             ("v2_autovec", None)]:
                r = (model_autovec_gemm(n, n, n, mc) if kp is None
                     else model_rvv_dgemm(n, n, n, kp, mc))
                rows.append([name, n, lanes, mc.vlen, f"{r.gflops:.3f}",
                             f"{r.peak_gflops:.2f}", f"{r.utilization*100:.1f}",
                             r.breakdown.get("bound", "")])
    w("e2_lanes.csv", ["variant", "N", "lanes", "VLEN", "GFLOPS", "peak", "util%", "bound"],
      rows)


# ---------------- E3: LMUL x MR 扫描 (L=16) ----------------
def e3_lmul_mr():
    rows = []
    mc = Ara2Config(lanes=16, freq_ghz=FREQ[16])
    for mr in (2, 4, 8, 16):
        for lmul in (1, 2, 4, 8):
            kp = KernelParams(mr=mr, lmul=lmul, kc=128)
            if kp.vregs_needed() > 40:
                continue
            r = model_rvv_dgemm(256, 256, 256, kp, mc)
            b = r.breakdown
            rows.append([mr, lmul, kp.vregs_needed(), "YES" if b["vregs_overflow"] else "no",
                         f"{r.gflops:.3f}", f"{r.utilization*100:.1f}", b["bound"]])
    w("e3_lmul_mr.csv", ["MR", "LMUL", "vregs", "VRF溢出", "GFLOPS", "util%", "bound"], rows)


# ---------------- E4: 多核对比 (总 lane=16) ----------------
def e4_multicore():
    rows = []
    for n in (64, 128, 256):
        for lanes in (16, 8, 4, 2):
            mc = Ara2Config(lanes=lanes, freq_ghz=1.0)
            kp = KernelParams(mr=4, lmul=1, kc=min(n, 64))
            r = model_multicore(n, n, n, kp, 16, mc)
            rows.append([n, 16 // lanes, lanes, f"{r.gflops:.3f}",
                         f"{r.peak_gflops:.2f}", f"{r.utilization*100:.1f}",
                         r.breakdown.get("bound", "")])
    w("e4_multicore.csv", ["N", "cores", "lanes/core", "GFLOPS", "peak", "util%", "bound"],
      rows)


# ---------------- E5: Linpack ----------------
def e5_linpack():
    rows = []
    for lanes in (2, 4, 8, 16):
        mc = Ara2Config(lanes=lanes, freq_ghz=FREQ[lanes])
        for n in (128, 256, 512, 1024):
            for tag, nb, kp in [
                ("nb32+mr8m2", 32, KernelParams(mr=8, lmul=2, kc=128)),
                ("nb64+mr8m2", 64, KernelParams(mr=8, lmul=2, kc=128)),
                ("nb32+mr4m1基线", 32, KernelParams(mr=4, lmul=1, kc=64)),
            ]:
                r = model_linpack(n, nb, kp, mc)
                b = r.breakdown
                rows.append([lanes, n, nb, kp.mr, kp.lmul, f"{r.gflops:.3f}",
                             f"{r.peak_gflops:.2f}", f"{r.utilization*100:.1f}",
                             f"{b['dgemm_share']*100:.1f}"])
    w("e5_linpack.csv",
      ["lanes", "N", "NB", "MR", "LMUL", "GFLOPS", "peak", "util%", "DGEMM占比%"], rows)


# ---------------- E6: 规模扫描（含小矩阵发射受限） ----------------
def e6_sizes():
    rows = []
    for lanes in (4, 16):
        mc = Ara2Config(lanes=lanes, freq_ghz=FREQ[lanes])
        for n in (32, 64, 128, 256, 512, 1024, 2048):
            kp = KernelParams(mr=8, lmul=2, kc=min(n, 128))
            r = model_rvv_dgemm(n, n, n, kp, mc)
            rows.append([lanes, n, f"{r.gflops:.3f}", f"{r.utilization*100:.1f}",
                         r.breakdown["bound"]])
    w("e6_sizes.csv", ["lanes", "N", "GFLOPS", "util%", "bound"], rows)


if __name__ == "__main__":
    e1_variants()
    e2_lanes()
    e3_lmul_mr()
    e4_multicore()
    e5_linpack()
    e6_sizes()
    print("ALL EXPERIMENTS DONE")
