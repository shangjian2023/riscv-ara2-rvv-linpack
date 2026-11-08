#!/usr/bin/env python3
"""Build report figures from archived CSV evidence; never invent chart values."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

# Fixed categorical palette, checked with the dataviz validator. Position, marker,
# direct labels and legends also encode identity; color is never the only cue.
COLORS = {
    "blue": "#2A78D6",
    "orange": "#EB6834",
    "green": "#1BAF7A",
    "yellow": "#EDA100",
}
TEXT = "#202020"
MUTED = "#52606D"
GRID = "#D8D8D8"
AXIS = "#505050"
SURFACE = "#F5F7FA"
BORDER = "#D9E1E8"
LANE_COLORS = {2: COLORS["blue"], 4: COLORS["orange"],
               8: COLORS["green"], 16: COLORS["yellow"]}
LANE_MARKERS = {2: "o", 4: "s", 8: "^", 16: "D"}


def configure_style():
    windows_font = Path("/mnt/c/Windows/Fonts/msyh.ttc")
    if windows_font.exists():
        font_manager.fontManager.addfont(str(windows_font))
        family = "Microsoft YaHei"
    else:
        family = "DejaVu Sans"
    matplotlib.rcParams.update(
        {
            "font.family": family,
            "font.size": 13,
            "axes.titlesize": 17,
            "axes.labelsize": 14,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 12,
            "axes.edgecolor": AXIS,
            "axes.labelcolor": TEXT,
            "text.color": TEXT,
            "xtick.color": AXIS,
            "ytick.color": AXIS,
            "axes.linewidth": 1.0,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "axes.unicode_minus": False,
        }
    )


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_data(name):
    return read_csv(HERE / name)


def save_all(fig, name):
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(HERE / f"{name}.{suffix}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"FIGURE {name}")


def millions_formatter(value, _position):
    return f"{value / 1_000_000:.1f}"


def add_box(ax, bounds, title, body, color, title_size=16, body_size=13):
    x1, y1, x2, y2 = bounds
    patch = FancyBboxPatch(
        (x1, y1), x2 - x1, y2 - y1,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        transform=ax.transAxes, facecolor=SURFACE, edgecolor=color, linewidth=1.8,
    )
    ax.add_patch(patch)
    ax.text((x1 + x2) / 2, y2 - 0.045, title, transform=ax.transAxes,
            ha="center", va="top", fontsize=title_size, color=TEXT)
    if body:
        ax.text((x1 + x2) / 2, y2 - 0.105, body, transform=ax.transAxes,
                ha="center", va="top", fontsize=body_size, color=MUTED,
                linespacing=1.5)


def add_arrow(ax, start, end, color=AXIS, style="-|>", linestyle="-"):
    arrow = FancyArrowPatch(
        start, end, transform=ax.transAxes, arrowstyle=style,
        mutation_scale=16, linewidth=1.6, color=color, linestyle=linestyle,
        shrinkA=3, shrinkB=3,
    )
    ax.add_patch(arrow)


def figure_pipeline():
    fig, ax = plt.subplots(figsize=(12.2, 7.0))
    ax.axis("off")
    add_box(ax, (0.07, 0.79, 0.56, 0.96), "同源 C / RVV 1.0 内核",
            "参数化双精度矩阵乘 + 自研Linpack求解程序", COLORS["blue"], 17, 14)
    add_box(ax, (0.66, 0.79, 0.96, 0.96), "官方 Netlib HPL 2.3",
            "独立公开源码 · 算法文件未修改", COLORS["orange"], 16, 13)

    middle = [
        ((0.03, 0.44, 0.29, 0.66), "QEMU / Spike", "多 VLEN 功能回归\nISA 语义与数值指纹", COLORS["green"]),
        ((0.37, 0.44, 0.63, 0.66), "Ara2 Verilator RTL", "裸机程序 · 周期计数\n2 / 4 / 8 / 16 条通道", COLORS["blue"]),
        ((0.71, 0.44, 0.97, 0.66), "CanMV-K230 / C908", "Linux 单 CPU\n同源内核分平台构建", COLORS["orange"]),
    ]
    for bounds, title, body, color in middle:
        add_box(ax, bounds, title, body, color, 15, 13)
    add_arrow(ax, (0.22, 0.79), (0.16, 0.67))
    add_arrow(ax, (0.34, 0.79), (0.50, 0.67))
    add_arrow(ax, (0.49, 0.79), (0.81, 0.67))
    add_arrow(ax, (0.81, 0.79), (0.87, 0.67), color=COLORS["orange"])

    add_box(ax, (0.08, 0.16, 0.48, 0.34), "统一证据归档",
            "原始日志 · ELF / 反汇编 · CSV · SHA-256", COLORS["blue"], 15, 13)
    add_box(ax, (0.56, 0.16, 0.92, 0.34), "自动校验",
            "周期与利用率 · 残差 · 校验和 / 数值指纹", COLORS["green"], 15, 13)
    for x in (0.16, 0.50, 0.84):
        add_arrow(ax, (x, 0.44), (0.30 if x < 0.65 else 0.73, 0.35))
    add_arrow(ax, (0.48, 0.25), (0.56, 0.25))

    ax.text(0.5, 0.065,
            "QEMU与C908共用Linux二进制；Ara2与C908采用同源代码分平台构建",
            transform=ax.transAxes, ha="center", fontsize=13, color=TEXT)
    ax.set_title("同源代码、分层实测、逐项对账", pad=12)
    save_all(fig, "fig_evaluation_pipeline")


def figure_optimization():
    dump = (ROOT / "apps_linpack_draft/results/local_rtl/4_lanes/"
            "n128_nb32_opt_panel_v2/linpack.dump").read_text(encoding="utf-8")
    for instruction in ("vlse64.v", "vsse64.v", "vfmacc.vf"):
        assert instruction in dump, f"missing disassembly evidence: {instruction}"

    fig = plt.figure(figsize=(12.2, 6.5))
    grid = fig.add_gridspec(1, 2, width_ratios=[1.55, 1], wspace=0.08,
                            left=0.035, right=0.98, top=0.85, bottom=0.10)
    ax_code = fig.add_subplot(grid[0, 0])
    ax_code.axis("off")
    ax_code.add_patch(FancyBboxPatch(
        (0, 0), 1, 1, boxstyle="round,pad=0.02", transform=ax_code.transAxes,
        facecolor="#111820", edgecolor="#111820"))
    code = (
        "vl = vsetvl_e64m4(hi - offset);\n"
        "pivot = vle64(&A[c, offset], vl);\n"
        "for (r = c + 1; r < n; r++) {\n"
        "  vd = vle64(&A[r, offset], vl);\n"
        "  vd = vfmacc(vd, -A[r,c], pivot, vl);\n"
        "  vse64(&A[r, offset], vd, vl);\n"
        "}"
    )
    ax_code.text(0.055, 0.88, code, transform=ax_code.transAxes,
                 family="DejaVu Sans Mono", fontsize=13.5, color="#E6EDF3",
                 va="top", linespacing=1.75)
    ax_code.plot([0.055, 0.94], [0.29, 0.29], transform=ax_code.transAxes,
                 color="#405061", linewidth=1.2)
    ax_code.text(0.055, 0.22,
                 "优化前：每一行都重复装载主元行\n"
                 "优化后：主元行驻留向量寄存器，跨行复用",
                 transform=ax_code.transAxes, fontsize=13.5,
                 color="#A9D6C5", va="top", linespacing=1.65)
    ax_code.set_title("第二轮列分块优化核心伪代码", color=TEXT, fontsize=16, pad=14)

    ax = fig.add_subplot(grid[0, 1])
    ax.axis("off")
    ax.text(0.03, 0.95, "真实 RVV 反汇编", transform=ax.transAxes,
            fontsize=17, va="top")
    instructions = [
        ("vlse64.v  v4,(a5),s1", "跨步装载"),
        ("vsse64.v  v4,(a5),s1", "跨步存回"),
        ("vfmacc.vf v4,fa5,v8", "向量乘加"),
    ]
    for index, (instruction, meaning) in enumerate(instructions):
        y = 0.77 - index * 0.19
        ax.add_patch(FancyBboxPatch(
            (0.02, y - 0.09), 0.96, 0.13, boxstyle="round,pad=0.012",
            transform=ax.transAxes, facecolor=SURFACE, edgecolor=BORDER))
        ax.text(0.06, y, instruction, transform=ax.transAxes,
                family="DejaVu Sans Mono", fontsize=12.5, color=COLORS["blue"], va="center")
        ax.text(0.06, y - 0.055, meaning, transform=ax.transAxes,
                fontsize=11.5, color=MUTED, va="center")
    ax.text(0.03, 0.19,
            "主元行跨多个待更新行复用\nRVV 整行交换与列缩放\n残差与校验和保持不变",
            transform=ax.transAxes, fontsize=14, va="top", linespacing=1.65)
    fig.suptitle("瓶颈优化落实到真实RVV指令", fontsize=18, y=0.97)
    fig.text(0.5, 0.025,
             "反汇编来源：n128_nb32_opt_panel_v2/linpack.dump；前两列对应列缩放，vfmacc.vf 对应行更新",
             ha="center", fontsize=11.5, color=MUTED)
    save_all(fig, "fig_panel_v2_evidence")


def figure_fullchain():
    rows = read_csv(ROOT / "apps_linpack_draft/results/local_linpack_summary.csv")
    selected = [r for r in rows if r["profiled"] == "0" and r["lanes"] == "4"
                and r["NB"] == "32" and r["mr"] == "8" and r["lmul"] == "2"
                and r["kc"] == "128" and r["pipe"] == "0" and r["N"] in ("128", "256")]
    assert len(selected) == 6, f"expected six unprofiled full-chain rows, got {len(selected)}"
    variants = ["baseline", "rvv_phases", "panel_v2"]
    labels = ["基线版本", "第一轮\n阶段向量化", "第二轮\n列分块优化"]
    colors = [COLORS["orange"], COLORS["blue"], COLORS["green"]]
    by_key = {(int(r["N"]), r["variant"]): r for r in selected}

    fig, axes = plt.subplots(1, 2, figsize=(11.4, 5.6))
    x = np.arange(3)
    for ax, n in zip(axes, (128, 256)):
        cycles = np.array([int(by_key[(n, variant)]["cycles"]) for variant in variants]) / 1e6
        utils = [float(by_key[(n, variant)]["util"]) for variant in variants]
        baseline = cycles[0]
        for index in range(2):
            ax.annotate("", xy=(x[index + 1], cycles[index + 1]),
                        xytext=(x[index], cycles[index]),
                        arrowprops={"arrowstyle": "-|>", "color": AXIS,
                                    "linewidth": 2.0, "shrinkA": 12, "shrinkB": 12})
        ax.scatter(x, cycles, s=150, c=colors, edgecolor="white", linewidth=1.5, zorder=3)
        for index, (cycle, util, variant) in enumerate(zip(cycles, utils, variants)):
            speedup = baseline / cycle
            speedup_text = f" · {speedup:.2f}×" if index else ""
            label = f"{cycle:.2f} 百万周期\n利用率 {util:.2f}%{speedup_text}"
            if index == 1:
                ax.annotate(label, (x[index], cycle), xytext=(-12, -28),
                            textcoords="offset points", ha="right", va="top",
                            fontsize=11.5, linespacing=1.45)
            else:
                ax.annotate(label, (x[index], cycle), xytext=(0, 28),
                            textcoords="offset points", ha="center", va="bottom",
                            fontsize=11.5, linespacing=1.45)
        ax.set_xticks(x, labels)
        ax.set_ylim(0, baseline * 1.28)
        ax.set_xlim(-0.38, 2.38)
        ax.set_ylabel("Linpack求解周期（百万）")
        ax.set_title(f"{n}阶：{baseline:.2f} → {cycles[-1]:.2f} 百万周期，加速 {baseline / cycles[-1]:.2f}×",
                     fontsize=15, pad=12)
        ax.grid(axis="x", visible=False)
    fig.suptitle("同一优化路径在两种矩阵规模上均持续降低求解周期", fontsize=18, y=0.99)
    fig.text(0.5, 0.02, "Ara2四条向量通道，分块32；关闭分阶段计时；加速比均相对各自基线版本",
             ha="center", fontsize=11.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.065, 1, 0.94))
    save_all(fig, "fig_fullchain_n128_n256")


def figure_n128():
    rows = read_data("figure_data_n128.csv")
    by_key = {(row["stage"], row["variant"]): int(row["cycles"]) for row in rows}
    stages = ["Panel LU", "U12 update", "Trailing DGEMM", "Triangular solve"]
    stage_labels = ["按列分块更新", "右上矩阵块更新", "尾部矩阵乘", "三角求解"]
    baseline = np.array([by_key[(stage, "baseline")] for stage in stages]) / 1e6
    optimized = np.array([by_key[(stage, "optimized")] for stage in stages]) / 1e6
    y = np.arange(len(stages))[::-1]

    fig, ax = plt.subplots(figsize=(10.4, 5.9))
    for index, ypos in enumerate(y):
        ax.annotate("", xy=(optimized[index], ypos), xytext=(baseline[index], ypos),
                    arrowprops={"arrowstyle": "-|>", "color": AXIS, "linewidth": 2.0,
                                "shrinkA": 10, "shrinkB": 10})
        reduction = (1 - optimized[index] / baseline[index]) * 100
        reduction_text = f"减少 {reduction:.1f}%" if abs(reduction) >= 1.0 else "基本持平"
        ax.text(4.43, ypos, reduction_text,
                ha="right", va="center", fontsize=12.5, color=TEXT)
    ax.scatter(baseline, y, s=130, color=COLORS["orange"], edgecolor="white",
               linewidth=1.3, label="基线版本", zorder=3)
    ax.scatter(optimized, y, s=130, color=COLORS["blue"], edgecolor="white",
               linewidth=1.3, label="第二轮列分块优化", zorder=3)
    for index, ypos in enumerate(y):
        ax.annotate(f"{baseline[index]:.2f}", (baseline[index], ypos), xytext=(0, 11),
                    textcoords="offset points", ha="center", fontsize=11.5, color=TEXT)
        ax.annotate(f"{optimized[index]:.2f}", (optimized[index], ypos), xytext=(0, -20),
                    textcoords="offset points", ha="center", fontsize=11.5, color=TEXT)
    total_base = by_key[("Total", "baseline")] / 1e6
    total_opt = by_key[("Total", "optimized")] / 1e6
    fig.text(0.97, 0.91, f"全过程：{total_base:.2f} → {total_opt:.2f} 百万周期\n"
                        f"减少 {(1 - total_opt / total_base) * 100:.1f}%，加速 {total_base / total_opt:.2f}×",
             ha="right", va="top", fontsize=12.5, linespacing=1.5,
             bbox={"boxstyle": "round,pad=0.45", "facecolor": SURFACE, "edgecolor": BORDER})
    ax.set_yticks(y, stage_labels)
    ax.set_xlabel("阶段周期（百万）")
    ax.set_xlim(0, 4.55)
    ax.set_ylim(-0.65, 3.55)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", ncol=2)
    fig.suptitle("128阶矩阵：第二轮优化集中压缩两个关键阶段", fontsize=18, y=0.99)
    fig.text(0.5, 0.015, "两次运行均开启分阶段计时；箭头从基线版本指向第二轮列分块优化",
             ha="center", fontsize=11.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.055, 1, 0.82))
    save_all(fig, "fig_n128_cycle_breakdown")


def figure_anchor_scaling():
    cloud = read_csv(ROOT / "apps_linpack_draft/results/cloud_all.csv")
    lanes = [2, 4, 8, 16]
    anchor = []
    for lane in lanes:
        row = next(r for r in cloud if r["phase"] == "e0" and r["var"] == "fmatmul"
                   and r["config"] == f"{lane}_lanes" and r["N"] == "64")
        cycles = int(row["cycles"])
        anchor.append(100.0 * (2.0 * 64**3 / cycles) / (2 * lane))
    dgemm = []
    best_rows = []
    for lane in lanes:
        candidates = [r for r in cloud if r["job"].startswith("e3_")
                      and r["config"] == f"{lane}_lanes" and r["var"] == "rvv"
                      and r["N"] == "256" and r["kc"] == "128"]
        best = max(candidates, key=lambda r: float(r["util"]))
        best_rows.append(best)
        dgemm.append(float(best["util"]))
    assert [round(v, 2) for v in anchor] == [93.42, 93.08, 73.98, 47.11]
    assert [round(v, 2) for v in dgemm] == [63.86, 64.05, 54.93, 41.87]

    fig, ax = plt.subplots(figsize=(9.6, 5.8))
    x = np.arange(len(lanes))
    ax.plot(x, anchor, "o-", color=COLORS["blue"], linewidth=2.2, markersize=8,
            markeredgecolor="white", markeredgewidth=1.0, label="官方 fmatmul 64³")
    ax.plot(x, dgemm, "s-", color=COLORS["orange"], linewidth=2.2, markersize=8,
            markeredgecolor="white", markeredgewidth=1.0, label="自研双精度矩阵乘 N=256 已测最优")
    for series, offsets in ((anchor, (0, 9)), (dgemm, (0, -20))):
        for index, value in enumerate(series):
            ax.annotate(f"{value:.2f}%", (x[index], value), xytext=offsets,
                        textcoords="offset points", ha="center", fontsize=11.5)
    ax.axhline(94, color=AXIS, linestyle="--", linewidth=1.2)
    ax.text(3.35, 95.2, "Ara2 论文 fmatmul 64³：94%", ha="right", fontsize=11.5, color=MUTED)
    ax.set_xticks(x, [f"{lane}\nVLEN {lane * 1024}" for lane in lanes])
    ax.set_xlabel("Ara2 通道数 / 向量寄存器位宽（bit）")
    ax.set_ylabel("峰值利用率（%）")
    ax.set_ylim(0, 108)
    ax.set_xlim(-0.25, 3.35)
    ax.legend(loc="lower left", ncol=2)
    ax.set_title("官方基准与自研内核的平台缩放特征", pad=12)
    fig.text(0.5, 0.015, "官方基准用于环境校验，自研矩阵乘用于优化分析；矩阵乘每档取同归档已测最优配置",
             ha="center", fontsize=11.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    save_all(fig, "fig_anchor_dgemm_scaling")


def figure_model():
    rows = read_csv(ROOT / "apps_linpack_draft/results/e8_cloud/e8_error.csv")
    rvv = [r for r in rows if r["var"] == "rvv"]
    assert len(rvv) == 49
    average = -sum(float(r["err_cycles_pct"]) for r in rvv) / len(rvv)
    ceiling = sum(float(r["model_util_pct"]) >= 95 and float(r["meas_util_pct"]) < 80 for r in rvv)
    assert round(average, 1) == 52.4 and ceiling == 37

    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    for lane in (2, 4, 8, 16):
        selected = [r for r in rvv if int(r["lanes"]) == lane]
        ax.scatter([float(r["meas_cycles"]) for r in selected],
                   [float(r["model_cycles"]) for r in selected],
                   s=58, alpha=0.80, color=LANE_COLORS[lane], marker=LANE_MARKERS[lane],
                   edgecolor="white", linewidth=0.7, label=f"{lane} 条通道（{len(selected)} 点）")
    limits = [6.5e5, 4.2e7]
    ax.plot(limits, limits, color=AXIS, linestyle="--", linewidth=1.5)
    ax.plot(limits, [value / 2 for value in limits], color=MUTED, linestyle=":", linewidth=1.8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(*limits)
    ax.set_ylim(6.5e5, 1.45e7)
    ax.set_xlabel("RTL 实测周期（Verilator mcycle）")
    ax.set_ylabel("理论推算周期")
    ax.text(1.25e6, 4.8e6, "y = x", rotation=35, fontsize=12, color=AXIS)
    ax.text(8.0e6, 2.6e6, "y = x / 2", rotation=31, fontsize=12, color=MUTED)
    ax.text(0.035, 0.965, "49 个手写 RVV 点\n平均低估周期 52.4%\n37 / 49 点出现“接近峰值”假象",
            transform=ax.transAxes, va="top", fontsize=12.5, linespacing=1.5,
            bbox={"boxstyle": "round,pad=0.5", "facecolor": "white", "edgecolor": BORDER})
    ax.legend(loc="lower right", ncol=2)
    ax.set_title("49组RTL实测建立理论推算的校准依据", pad=12)
    fig.text(0.5, 0.015, "每个点为一组手写RVV矩阵乘配置；对数坐标；数据来源：e8_error.csv",
             ha="center", fontsize=11.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save_all(fig, "fig_model_rtl_scatter")


def figure_k230():
    rows = read_data("figure_data_k230.csv")
    ns = [160, 256, 512, 1024]
    gflops = {
        variant: [float(row["gflops"]) for row in rows if row["variant"] == variant]
        for variant in ("unpacked", "B-packed")
    }
    gains = [packed / unpacked for unpacked, packed in zip(gflops["unpacked"], gflops["B-packed"])]
    x = np.arange(len(ns))

    fig, ax = plt.subplots(figsize=(9.5, 5.7))
    ax.plot(x, gflops["unpacked"], "o-", linewidth=2.2, markersize=8,
            color=COLORS["orange"], markeredgecolor="white", markeredgewidth=1.0, label="未打包")
    ax.plot(x, gflops["B-packed"], "s-", linewidth=2.2, markersize=8,
            color=COLORS["blue"], markeredgecolor="white", markeredgewidth=1.0, label="B矩阵分块打包")
    for index, gain in enumerate(gains):
        lower = min(gflops["unpacked"][index], gflops["B-packed"][index])
        ax.annotate(f"{gain:.2f}×", xy=(x[index], lower), xytext=(-4, 10),
                    textcoords="offset points", ha="right", fontsize=12)
    ax.set_xticks(x, [str(value) for value in ns])
    ax.set_xlabel("矩阵规模 N")
    ax.set_ylabel("双精度矩阵乘中位吞吐（GFLOP/s）")
    ax.set_ylim(0, 1.5)
    ax.set_xlim(-0.28, 3.35)
    ax.legend(loc="upper right")
    ax.set_title("K230：B矩阵打包改善大矩阵的访存性能", pad=12)
    fig.text(0.5, 0.015, "N=160/256/512/1024 分别重复 15/13/9/5 次；标注为相同矩阵规模的打包收益",
             ha="center", fontsize=11.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    save_all(fig, "fig_k230_pack_b")


def figure_hpl():
    rows = read_data("figure_data_hpl.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 5.5), gridspec_kw={"width_ratios": [1, 1.65]})

    ax = axes[0]
    blas_rows = [row for row in rows if row["comparison"] == "Same-shape BLAS"]
    values = [float(row["gflops"]) for row in blas_rows]
    ax.annotate("", xy=(1, values[1]), xytext=(0, values[0]),
                arrowprops={"arrowstyle": "-|>", "color": AXIS, "linewidth": 2.2,
                            "shrinkA": 12, "shrinkB": 12})
    ax.scatter([0, 1], values, s=160, c=[COLORS["orange"], COLORS["blue"]],
               edgecolor="white", linewidth=1.5, zorder=3)
    for index, value in enumerate(values):
        offset = 10 if index else -24
        ax.annotate(f"{value:.3f}", (index, value), xytext=(0, offset),
                    textcoords="offset points", ha="center", fontsize=12.5)
    ax.text(0.5, 0.80, "6.39×", ha="center", fontsize=15, color=TEXT,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": SURFACE, "edgecolor": BORDER})
    ax.set_xticks([0, 1], ["Reference\nBLAS", "OpenBLAS\nRVV"])
    ax.set_xlim(-0.42, 1.42)
    ax.set_ylim(0, 1.68)
    ax.set_title("1000阶：相同规模提升6.39倍", pad=10)
    ax.grid(axis="x", visible=False)

    ax = axes[1]
    scaling_rows = [row for row in rows if row["comparison"] == "OpenBLAS scaling"]
    styles = {
        "128": (COLORS["orange"], "o"),
        "256": (COLORS["blue"], "s"),
        "512": (COLORS["green"], "^"),
    }
    for nb, (color, marker) in styles.items():
        selected = [row for row in scaling_rows if row["NB"] == nb]
        x = [0 if row["N"] == "4096" else 1 for row in selected]
        values = [float(row["gflops"]) for row in selected]
        if len(selected) > 1:
            ax.plot(x, values, color=color, linewidth=2.0, alpha=0.8)
        ax.scatter(x, values, s=135, color=color, marker=marker, edgecolor="white",
                   linewidth=1.3, label=f"分块 {nb}", zorder=3)
        for xpos, value in zip(x, values):
            offset = 10 if nb == "256" else -24
            ax.annotate(f"{value:.4f}", (xpos, value), xytext=(0, offset),
                        textcoords="offset points", ha="center", fontsize=11.5)
    ax.set_xticks([0, 1], ["4096阶", "8192阶"])
    ax.set_xlabel("矩阵规模")
    ax.set_xlim(-0.30, 1.30)
    ax.set_ylim(0, 2.15)
    ax.set_yticks([0, 0.5, 1.0, 1.5, 2.0])
    ax.set_title("OpenBLAS大规模实测", pad=10)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="lower left", ncol=3)

    fig.suptitle("K230官方HPL 2.3：单Linux CPU，全部通过残差校验", y=0.99, fontsize=17)
    fig.supylabel("HPL吞吐（GFLOP/s）", fontsize=14)
    fig.text(0.5, 0.025, "4096阶、分块256为三次中位数；8192阶为单次测量；左图为相同规模的单次BLAS对比",
             ha="center", fontsize=11.5, color=MUTED)
    fig.tight_layout(rect=(0.055, 0.10, 1, 0.94))
    save_all(fig, "fig_hpl_openblas")


def main():
    configure_style()
    figure_pipeline()
    figure_optimization()
    figure_fullchain()
    figure_n128()
    figure_anchor_scaling()
    figure_model()
    figure_k230()
    figure_hpl()
    print(f"Generated eight figures in {HERE}")


if __name__ == "__main__":
    main()
