#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""charts.py - 报告图表生成（中文标注，Windows 字体经 /mnt/c 注册）。"""
import csv
import os
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")

# 注册 Windows 中文字体（在 WSL 中运行）
for fp in ("/mnt/c/Windows/Fonts/msyh.ttc", "/mnt/c/Windows/Fonts/simhei.ttf",
           "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
    if os.path.exists(fp):
        font_manager.fontManager.addfont(fp)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=fp).get_name()
        break
plt.rcParams["axes.unicode_minus"] = False

C_VEC = "#2b6cb0"     # 主色
C_AUTO = "#48bb78"
C_SCALAR = "#a0aec0"
C_WARN = "#e53e3e"
C_PEAK = "#e68a00"


def read(name):
    with open(os.path.join(RES, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def f1_variants():
    rows = read("e1_variants.csv")
    names = ["v0_scalar", "v2_autovec", "v3_rvv_mr4_m1_kc64", "v4_rvv_mr8_m2_kc128",
             "v5_pipe_mr8_m2_kc128", "v4_rvv_mr16_m2_kc128(溢出)",
             "v4_rvv_mr8_m4_kc128(溢出)"]
    labels = ["v0\n标量基线", "v2\n自动向量化", "v3\nRVV基础", "v4\nRVV调优",
              "v5\n+软件流水", "mr16×m2\n(VRF溢出)", "mr8×m4\n(VRF溢出)"]
    g = [float(next(r for r in rows if r["variant"] == n)["GFLOPS"]) for n in names]
    colors = [C_SCALAR, C_AUTO, C_VEC, C_VEC, C_VEC, C_WARN, C_WARN]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.bar(labels, g, color=colors)
    ax.axhline(34.56, color=C_PEAK, ls="--", lw=1.2)
    ax.text(6.45, 34.9, "Ara2 16-lane 峰值 34.56 GFLOPS", color=C_PEAK, fontsize=9,
            ha="right")
    for b, v in zip(bars, g):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.5, f"{v:.1f}", ha="center",
                fontsize=9)
    ax.set_ylabel("GFLOPS @1.08 GHz")
    ax.set_title("图1  DGEMM 优化变体对比（N=256, FP64, Ara2 软件模型）")
    ax.set_ylim(0, 40)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "f1_variants.png"), dpi=150)


def f2_lanes():
    rows = read("e2_lanes.csv")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for n, mk, lb in [(1024, "o-", "v4 手写RVV N=1024"), (1024, "s--", "v2 自动向量化 N=1024"),
                      (256, "o:", "v4 手写RVV N=256")]:
        sel = [r for r in rows if r["variant"] == ("v4" if "v4" in lb else "v2_autovec")
               and int(r["N"]) == n]
        sel.sort(key=lambda r: int(r["lanes"]))
        x = [int(r["lanes"]) for r in sel]
        y = [float(r["GFLOPS"]) for r in sel]
        ax.plot(x, y, mk, label=lb, markersize=5,
                color=C_VEC if "v4" in lb else C_AUTO)
    peak = [(2, 5.4), (4, 10.8), (8, 21.6), (16, 34.56)]
    ax.plot(*zip(*peak), "^-", color=C_PEAK, label="理论峰值 (2L FLOP/cyc × f)", lw=1.2)
    ax.set_xticks([2, 4, 8, 16])
    ax.set_xlabel("Ara2 lane 数 L（VLEN = 1024L bit）")
    ax.set_ylabel("GFLOPS")
    ax.set_title("图2  Lane 扩展性：手写 RVV 内核在两种规模下均贴近峰值")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "f2_lanes.png"), dpi=150)


def f3_lmul_mr():
    rows = read("e3_lmul_mr.csv")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    mrs = [2, 4, 8, 16]
    width = 0.2
    for i, lm in enumerate([1, 2, 4, 8]):
        xs, ys = [], []
        for mr in mrs:
            r = next((r for r in rows if int(r["MR"]) == mr and int(r["LMUL"]) == lm), None)
            if r:
                xs.append(mrs.index(mr) + i * width)
                ys.append(float(r["util%"]))
        hatch = "//" if lm >= 4 else None
        ax.bar(xs, ys, width, label=f"LMUL={lm}", hatch=hatch,
               color=C_VEC, alpha=1.0 - 0.18 * i)
    ax.set_xticks([i + 1.5 * width for i in range(len(mrs))])
    ax.set_xticklabels([f"MR={m}" for m in mrs])
    ax.set_ylabel("峰值利用率 %")
    ax.set_ylim(0, 115)
    ax.axhline(100, color=C_PEAK, ls="--", lw=1)
    ax.text(3.3, 102, "100%", color=C_PEAK, fontsize=9)
    ax.set_title("图3  MR×LMUL 设计空间（N=256, L=16）：VRF 溢出区显著退化")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "f3_lmul_mr.png"), dpi=150)


def f4_multicore():
    rows = read("e4_multicore.csv")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    con = ["1×16", "2×8", "4×4", "8×2"]
    width = 0.25
    for i, n in enumerate([64, 128, 256]):
        sel = [r for r in rows if int(r["N"]) == n]
        sel.sort(key=lambda r: -int(r["lanes/core"]))
        ys = [float(r["GFLOPS"]) for r in sel]
        ax.bar([j + i * width for j in range(4)], ys, width, label=f"N={n}³",
               color=[C_VEC, C_AUTO, C_SCALAR][i])
    ax.axhline(32, color=C_PEAK, ls="--", lw=1.2)
    ax.text(3.4, 32.5, "16 lane 总峰值", color=C_PEAK, fontsize=9)
    ax.set_xticks([j + width for j in range(4)])
    ax.set_xticklabels(con)
    ax.set_ylabel("GFLOPS @1 GHz")
    ax.set_title("图4  多核对比（总 lane=16）：小矩阵下多小核缓解 CVA6 发射瓶颈")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "f4_multicore.png"), dpi=150)


def f5_linpack():
    rows = read("e5_linpack.csv")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for lanes, mk in [(2, "o:"), (4, "s-"), (8, "d-"), (16, "o-")]:
        sel = [r for r in rows if int(r["lanes"]) == lanes and "基线" not in
               r.get("NB", "") and r["NB"] == "64"]
        sel.sort(key=lambda r: int(r["N"]))
        if not sel:
            continue
        x = [int(r["N"]) for r in sel]
        y = [float(r["GFLOPS"]) for r in sel]
        ax.plot(x, y, mk, label=f"{lanes} lane", markersize=6)
    ax.set_xscale("log", base=2)
    ax.set_xticks([128, 256, 512, 1024])
    ax.set_xticklabels(["128", "256", "512", "1024"])
    ax.set_xlabel("Linpack 矩阵阶 N")
    ax.set_ylabel("Linpack GFLOPS（模型）")
    ax.set_title("图5  Linpack 整体性能（分块 LU + RVV DGEMM，nb=64）")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "f5_linpack.png"), dpi=150)


def f6_sizes():
    rows = read("e6_sizes.csv")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for lanes, mk in [(4, "s-"), (16, "o-")]:
        sel = [r for r in rows if int(r["lanes"]) == lanes]
        sel.sort(key=lambda r: int(r["N"]))
        x = [int(r["N"]) for r in sel]
        y = [float(r["util%"]) for r in sel]
        ax.plot(x, y, mk, label=f"L={lanes} lane", markersize=6)
        for r, xi, yi in zip(sel, x, y):
            if int(r["N"]) <= 64:
                ax.annotate(r["bound"], (xi, yi), textcoords="offset points",
                            xytext=(0, -14), fontsize=8, color=C_WARN)
    ax.set_xscale("log", base=2)
    ax.set_xlabel("矩阵阶 N")
    ax.set_ylabel("峰值利用率 %")
    ax.set_title("图6  规模扫描：小矩阵下 16-lane 退化为发射受限（issue-bound）")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "f6_sizes.png"), dpi=150)


def f7_compiler():
    """双编译器对比：自动向量化证据（GCC 13 全部失败 vs Clang 18 成功）"""
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.0))
    ax = axes[0]
    fns = ["dgemm_naive", "dgemm_blocked"]
    gcc_v = [0, 0]
    clang_v = [6, 6]
    x = range(2)
    ax.bar([i - 0.17 for i in x], gcc_v, 0.34, label="GCC 13.3", color=C_SCALAR)
    ax.bar([i + 0.17 for i in x], clang_v, 0.34, label="Clang 18.1", color=C_VEC)
    ax.set_xticks(x)
    ax.set_xticklabels(["朴素 ijk", "分块+自动向量化"])
    ax.set_ylabel("函数内向量指令数（条）")
    ax.set_title("(a) 自动向量化：GCC 全失败 / Clang 成功")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")

    ax = axes[1]
    fns2 = ["mr8_m2_p0", "mr8_m2_p1", "mr16_m2_p0"]
    gv = [34, 44, 75]
    cv = [53, 64, 103]
    x = range(3)
    ax.bar([i - 0.17 for i in x], gv, 0.34, label="GCC 13.3", color=C_SCALAR)
    ax.bar([i + 0.17 for i in x], cv, 0.34, label="Clang 18.1", color=C_VEC)
    ax.set_xticks(x)
    ax.set_xticklabels(fns2, fontsize=9)
    ax.set_ylabel("静态向量指令数（条）")
    ax.set_title("(b) 手写内核：两编译器均正确，代码形态不同")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")
    fig.suptitle("图7  双编译器 RVV 后端对比（数据来源：llvm-objdump 静态统计）")
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "f7_compiler.png"), dpi=150)


def f8_precision():
    """低精度误差-吞吐权衡（Ozaki-lite split-FP16）"""
    rows = read("e10_precision.csv")
    sel = [r for r in rows if int(r["lanes"]) == 16]
    fig, ax1 = plt.subplots(figsize=(8, 4.2))
    names = [r["格式"] for r in sel]
    gf = [float(r["该格式有效GFLOPS"]) for r in sel]
    err = [float(r["归一化误差(实测)"]) for r in sel]
    colors = [C_VEC, C_WARN, C_AUTO]
    bars = ax1.bar(names, gf, color=colors, width=0.5)
    for b, v in zip(bars, gf):
        ax1.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.1f}", ha="center",
                 fontsize=10)
    ax1.set_ylabel("有效 GFLOPS @1.08GHz（16-lane）")
    ax1.set_ylim(0, 160)
    ax2 = ax1.twinx()
    ax2.plot(names, [max(e, 1e-8) for e in err], "ko--", markersize=7)
    for i, e in enumerate(err):
        ax2.annotate(f"{e:.0e}", (i, max(e, 1e-8)),
                     textcoords="offset points", xytext=(18, 6), fontsize=9)
    ax2.set_ylabel("归一化误差（实测）")
    ax2.set_yscale("log")
    ax2.set_ylim(1e-8, 1e-2)
    ax1.set_title("图8  低精度误差-吞吐权衡：split2 恢复精度的同时保留 1.33x 吞吐\n"
                  "（吞吐：Ara2 模型；精度：x86/RVV 实测）")
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "f8_precision.png"), dpi=150)


if __name__ == "__main__":
    f1_variants(); f2_lanes(); f3_lmul_mr(); f4_multicore(); f5_linpack(); f6_sizes()
    f7_compiler(); f8_precision()
    print("CHARTS DONE ->", os.path.abspath(RES))
