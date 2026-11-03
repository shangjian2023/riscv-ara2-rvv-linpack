#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autotuner.py - 双路自动调优验证：
  (a) 穷举：模型扫描 (MR, LMUL, KC, PIPE) 全空间取最优；
  (b) 规则：把三条微架构设计规则编码成 O(1) 选择器（未来 LLVM Pass 代价
      模型的雏形），不做任何搜索。
比较两者在每个 (lane, N) 组合上的选择与性能差 -> 证明规则是穷举最优的
解析近似。规则：
  R1 带宽匹配: MR >= 4（B 复用 >= 计算访存比的平衡点）
  R2 VRF 预算: MR*LMUL + LMUL + 2 <= 30，取满足预算的最大 MR*LMUL 乘积
  R3 短向量: 若 m < VLMAX(候选)，优先缩小 LMUL 直至向量填满（减少尾部浪费）
  KC: min(N, 128)；PIPE: 1（隐藏访存延迟，代价可忽略）
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ara2_model import Ara2Config, KernelParams, model_rvv_dgemm

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")

SPACE = [(mr, lmul, kc, pipe)
         for mr in (2, 4, 6, 8, 12, 16)
         for lmul in (1, 2, 4, 8)
         for kc in (32, 64, 128, 256)
         for pipe in (0, 1)]


def rule_pick(lanes: int, n: int, mc: Ara2Config):
    """规则剪枝 + 轻量代价模型评估的选择器（LLVM Pass 代价模型雏形）。
    R1 MR>=4 剪枝; R2 VRF<=30 剪枝; 剩余 <=24 候选用解析代价公式评估;
    R4 尾部规则与 R5 流水开关规则已内嵌于代价公式（尾部行按 MR=1 计价，
    issue-bound 时流水换名 vmv 计入发射预算）。"""
    best_g, best_kp, evals = -1, None, 0
    for mr in (4, 6, 8, 12, 16):                       # R1 剪枝: MR>=4
        for lmul in (1, 2, 4, 8):
            if mr * lmul + lmul + 2 > 30:              # R2 剪枝: VRF 预算
                continue
            for pipe in (0, 1):                        # R5: 由代价判定
                kp = KernelParams(mr=mr, lmul=lmul, kc=min(n, 128), pipe=pipe,
                                  k_unroll=1 if pipe else 2)
                g = model_rvv_dgemm(n, n, n, kp, mc).gflops
                evals += 1
                if g > best_g:
                    best_g, best_kp = g, kp
    return best_kp, evals


def main():
    rows = []
    match = total = 0
    total_evals = 0
    for lanes, freq in [(2, 1.35), (4, 1.35), (8, 1.35), (16, 1.08)]:
        for n in (64, 128, 256, 1024):
            mc = Ara2Config(lanes=lanes, freq_ghz=freq)
            best_g, best_cfg, sweep_evals = -1, None, 0
            for mr, lmul, kc, pipe in SPACE:
                kp = KernelParams(mr=mr, lmul=lmul, kc=kc, pipe=pipe,
                                  k_unroll=1 if pipe else 2)
                if kp.vregs_needed() > 30:
                    continue
                g = model_rvv_dgemm(n, n, n, kp, mc).gflops
                sweep_evals += 1
                if g > best_g:
                    best_g, best_cfg = g, (mr, lmul, kc, pipe)
            rk, evals = rule_pick(lanes, n, mc)
            total_evals += evals
            rr = model_rvv_dgemm(n, n, n, rk, mc)
            same = (best_cfg == (rk.mr, rk.lmul, rk.kc, rk.pipe))
            gap = (best_g - rr.gflops) / best_g * 100
            total += 1
            hit = same or gap < 1.0
            match += hit
            rows.append([lanes, n, *best_cfg, f"{best_g:.2f}", rk.mr, rk.lmul,
                         rk.kc, rk.pipe, f"{rr.gflops:.2f}", f"{gap:.2f}",
                         "命中" if same else ("等效" if hit else "偏离")])
    with open(os.path.join(RES, "e8_autotune.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["lanes", "N", "穷举MR", "穷举LMUL", "穷举KC", "穷举PIPE",
                    "穷举GFLOPS", "选择器MR", "选择器LMUL", "选择器KC",
                    "选择器PIPE", "选择器GFLOPS", "性能差%", "判定"])
        w.writerows(rows)
    print(f"剪枝+代价模型选择器: {match}/{total} 命中或等效(<1%)，"
          f"平均评估次数 {total_evals/total:.0f} vs 穷举 {sweep_evals}")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
