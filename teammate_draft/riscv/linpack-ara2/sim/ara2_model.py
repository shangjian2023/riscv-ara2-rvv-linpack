#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ara2_model.py - Ara2 软件级周期近似性能模拟器（cycle-approximate analytical model）

微架构参数全部来自 Ara2 论文与开源仓库 ground truth:
  [1] Perotti et al., "Ara2: Exploring Single- and Multi-Core Vector Processing
      with an Efficient RVV 1.0 Compliant Open-Source Processor", IEEE TC 2024.
      - lanes L ∈ {2,4,8,16}, 每 lane 1024 bit VRF slice -> VLEN = 1024*L bit
      - 峰值: 每 lane 1 个 FP64 FMA/周期 -> 2L DP-FLOP/cycle (Table II)
      - VLSU 带宽: 4L Byte/cycle（计算侧需要 8L Byte/cycle -> 必须数据复用）
      - 主存 SRAM: 2M words x 4L B/word, 访问延迟 7 cycle
      - CVA6 每 4 周期发射 1 条向量指令（论文实测 issue-rate bound）
      - 无向量 L1/L2 缓存; VRF 是唯一片上复用层 (32 个向量寄存器)
  [2] github.com/pulp-platform/ara config/{2,4,8,16}_lanes.mk: vlen=1024*lanes

模型原理（三层资源上限 + 指令级调度）:
  对每个 DGEMM 微内核 (MR, LMUL, KC, PIPE)，按其实际生成的指令流
  （静态反汇编校验）解析构造每 k 步的资源占用:
    issue : CVA6 向量指令发射通路  4 cycle/条
    fpu   : lane 阵列 FMA 吞吐     ceil(VL/L) cycle/条向量FMA
    vlsu  : 向量访存带宽           8*VL/(4L) cycle/条向量load
  内核稳态周期 = max(issue, fpu, vlsu)，再叠加 C 矩阵 load/store 摊销、
  A 面板打包标量开销、尾部损耗、以及 VRF 溢出惩罚(MR*LMUL+LMUL>30 时按
  反汇编实测栈流量计入)。
"""
import math
from dataclasses import dataclass, field
from typing import Optional

EPS = 1e-9


@dataclass
class Ara2Config:
    lanes: int = 4                 # 每核向量 lane 数 L
    cores: int = 1                 # 核数（多核 = 多个 CVA6+Ara2 簇）
    issue_interval: int = 4        # CVA6 发射 1 条向量指令的周期间隔 (论文实测)
    fma_per_lane: float = 1.0      # 每 lane 每周期 FP64 FMA 数
    vlsu_bytes_per_lane: float = 4.0   # 单位步长向量访存 B/cycle/lane
    mem_latency: int = 7           # SRAM 访问延迟 (cycle)
    vrf_regs: int = 32             # 向量寄存器个数
    freq_ghz: float = 1.0          # 频率 (GHz)，论文 TT 2/4/8 lane=1.35, 16 lane=1.08
    spill_cycles_per_kstep: int = 0    # VRF 溢出时每 k 步额外栈往返（0=无溢出）

    @property
    def vlen(self) -> int:         # VLEN (bit)
        return 1024 * self.lanes

    @property
    def vlen_elem_f64(self) -> int:    # FP64 元素数 / m1 向量寄存器
        return self.vlen // 64

    @property
    def peak_flops_per_cycle(self) -> float:
        return 2.0 * self.fma_per_lane * self.lanes * self.cores


@dataclass
class KernelParams:
    mr: int = 8        # C 行方向的寄存器分块（每 k 步 B 向量复用次数）
    lmul: int = 2      # LMUL 组长度
    kc: int = 128      # k 面板深度（C 累加器驻留 VRF 的深度）
    pipe: int = 0      # 软件流水（预取 B(k+1)，每 k 步多 1 条 vmv）
    k_unroll: int = 2  # 编译器对 k 循环的展开倍数（反汇编实测 p0=2, p1=1）

    def vregs_needed(self) -> int:
        # 累加器 MR*LMUL + B 缓冲 LMUL + 少量临时
        return self.mr * self.lmul + self.lmul + 2


@dataclass
class ModelResult:
    cycles: float
    flops: float
    gflops: float
    peak_gflops: float
    utilization: float           # 占峰值比例
    breakdown: dict = field(default_factory=dict)
    note: str = ""


def _ceil_div(a, b):
    return -(-a // b)


def model_rvv_dgemm(n: int, m: int, k: int, kp: KernelParams, mc: Ara2Config,
                    per_core: bool = False) -> ModelResult:
    """手写 RVV 内核 (v3/v4/v5) 的周期模型。per_core=True 时输出单核周期
    （多核行块划分在 model_multicore 中处理负载不均衡）。
    注意 Ara 的关键结构性质: VLEN = 1024*L -> 每条满宽 m1 向量指令的
    每 lane 工作量恒为 16 周期，与 lane 数无关；只有当 m < VLMAX（短向量，
    典型为小矩阵）时，大 lane 配置才退化为 CVA6 发射受限。"""
    L = mc.lanes
    cores = 1 if per_core else mc.cores
    vlmax = mc.vlen_elem_f64 * kp.lmul       # LMUL 组内 FP64 元素数
    flops = 2.0 * n * m * k

    # ---- j 方向块结构: 每块实际向量长度 vl_b ----
    j_blocks = _ceil_div(m, vlmax)
    blocks = [min(vlmax, m - b * vlmax) for b in range(j_blocks)]
    avg_lane_time = sum(_ceil_div(vl_b, L) for vl_b in blocks) / j_blocks  # 每条 vfmacc 平均 lane 周期
    avg_vl = m / j_blocks

    # ---- 每 k 步的指令流（与反汇编对齐）----
    vec_per_k = 1 + kp.mr + (1 if kp.pipe else 0)   # B load + MR vfmacc + (vmv)
    vec_per_k += 2.0 * kp.mr / kp.kc                # C 面板 load/store 摊销
    scalar_per_k = 3.0 / kp.k_unroll + kp.mr        # A 面板标量取数 fld + 地址/分支

    issue_per_k = vec_per_k * mc.issue_interval + scalar_per_k
    fma_per_k = kp.mr * avg_lane_time
    vlsu_per_k = (8 * avg_vl) / (mc.vlsu_bytes_per_lane * L) \
        + (2 * kp.mr * avg_vl * 8 / (mc.vlsu_bytes_per_lane * L)) / kp.kc

    steady = max(issue_per_k, fma_per_k, vlsu_per_k)

    # ---- i 尾行 (MR=1) 损耗: B 复用从 MR 降到 1 ----
    i_tail = n % kp.mr
    i_blocks = n // kp.mr
    if i_blocks > 0:
        tail_cycles = (n // kp.mr and i_tail) and (k * j_blocks * i_tail * (avg_lane_time + issue_per_k)) or 0
    else:
        tail_cycles = 0

    # ---- VRF 溢出惩罚（MR*LMUL+LMUL>30 时，栈往返按反汇编实测近似）----
    vregs = kp.vregs_needed()
    spill_per_k = 0.0
    if vregs > mc.vrf_regs:
        spill_per_k = min((vregs - mc.vrf_regs) * 8, fma_per_k)
    cycles_per_k = steady + spill_per_k

    # ---- 总周期 ----
    cycles = j_blocks * i_blocks * k * cycles_per_k + tail_cycles
    cycles /= cores

    gflops = flops / cycles * mc.freq_ghz
    peak = mc.peak_flops_per_cycle * mc.freq_ghz
    breakdown = {
        "issue": issue_per_k, "fpu": fma_per_k, "vlsu": vlsu_per_k,
        "steady": cycles_per_k, "spill": spill_per_k, "avg_vl": avg_vl,
        "j_blocks": j_blocks,
        "bound": ("issue" if issue_per_k >= max(fma_per_k, vlsu_per_k) - EPS else
                  "fpu" if fma_per_k >= vlsu_per_k - EPS else "vlsu"),
        "vregs": vregs, "vregs_overflow": vregs > mc.vrf_regs,
    }
    return ModelResult(cycles=cycles, flops=flops, gflops=gflops, peak_gflops=peak,
                       utilization=gflops / peak if peak > 0 else 0.0,
                       breakdown=breakdown)


def model_autovec_gemm(n: int, m: int, k: int, mc: Ara2Config) -> ModelResult:
    """v2: GCC 自动向量化 ijk 循环。编译器只会沿 j 做单位步长向量化，
    B 行每个 (i,l) 组合重新加载一次（复用=1），受 VLSU 带宽限制 ~50% 峰值，
    且分块不改变向量寄存器中的复用结构。"""
    L, cores = mc.lanes, mc.cores
    vlmax = mc.vlen_elem_f64
    j_blocks = _ceil_div(m, vlmax)
    flops = 2.0 * n * m * k
    # 每 (i, l, j块): 1 vfmacc + 1 load + 循环开销 ~4 标量（无展开优化时的保守值）
    issue = (2 * mc.issue_interval + 4) * n * k * j_blocks
    fpu = n * k * _ceil_div(vlmax, L) * j_blocks * 1.0
    vlsu = n * k * j_blocks * (8 * vlmax) / (mc.vlsu_bytes_per_lane * L)
    cycles = max(issue, fpu, vlsu) / cores
    gflops = flops / cycles * mc.freq_ghz
    peak = mc.peak_flops_per_cycle * mc.freq_ghz
    breakdown = {"issue": issue / (n * k * j_blocks), "fpu": fpu / (n * k * j_blocks),
                 "vlsu": vlsu / (n * k * j_blocks),
                 "bound": "issue" if issue >= max(fpu, vlsu) else
                          ("fpu" if fpu >= vlsu else "vlsu")}
    return ModelResult(cycles=cycles, flops=flops, gflops=gflops, peak_gflops=peak,
                       utilization=gflops / peak if peak > 0 else 0.0,
                       breakdown=breakdown)


def model_scalar_gemm(n: int, m: int, k: int, mc: Ara2Config) -> ModelResult:
    """v0: 纯标量 CVA6。FP64 乘加非融合、每周期 ~1 FLOP（保守），且每 FMA
    需 2 次标量取数 -> 受 CVA6 标量发射限制。"""
    cores = mc.cores
    flops = 2.0 * n * m * k
    cycles = 2.0 * n * m * k / cores        # 每 FLOP 约 1 cycle（取数+乘加）
    gflops = flops / cycles * mc.freq_ghz
    peak = mc.peak_flops_per_cycle * mc.freq_ghz
    return ModelResult(cycles=cycles, flops=flops, gflops=gflops, peak_gflops=peak,
                       utilization=gflops / peak if peak > 0 else 0.0,
                       breakdown={"bound": "scalar-issue"}, note="纯标量基线")


def model_multicore(n: int, m: int, k: int, kp: KernelParams, total_lanes: int,
                    mc: Ara2Config) -> ModelResult:
    """多核（论文核心结论: 8x2-lane 优于 1x16-lane，缓解标量发射瓶颈）。
    行块划分，含行尾不均衡损耗。"""
    assert total_lanes % mc.lanes == 0 or mc.lanes % total_lanes == 0
    ncores = total_lanes // mc.lanes
    sub = Ara2Config(**{**mc.__dict__, "cores": 1})
    per = model_rvv_dgemm(n, m, k, kp, sub, per_core=True)
    # 行块划分：每核分 ceil(i_blocks/ncores) 个 MR 块 -> 尾核不均衡
    blocks_per_core = _ceil_div(max(n // kp.mr, 1), ncores)
    slowest_rows = min(n, blocks_per_core * kp.mr)
    imbalance = slowest_rows / (n / ncores) if n > 0 else 1.0
    cycles = per.cycles * max(1.0, imbalance) / ncores
    flops = 2.0 * n * m * k
    peak = 2.0 * total_lanes * mc.freq_ghz
    gflops = flops / cycles * mc.freq_ghz
    return ModelResult(cycles=cycles, flops=flops, gflops=gflops, peak_gflops=peak,
                       utilization=gflops / peak if peak > 0 else 0.0,
                       breakdown=dict(per.breakdown,
                                     ncores=ncores, imbalance=imbalance),
                       note=f"{ncores}x{mc.lanes}lane")


def model_linpack(n: int, nb: int, kp: KernelParams, mc: Ara2Config) -> ModelResult:
    """Linpack 整体 = RVV-DGEMM 尾随更新 + 标量面板分解/三角求解 (Amdahl)。
    面板与 U12 前代为 CVA6 标量侧 ~1 FLOP/cycle；DGEMM 部分用上面的内核模型。"""
    L = mc.lanes
    dgemm_flops = 0.0
    panel_flops = 0.0
    k0 = 0
    while k0 < n:
        kb = min(nb, n - k0)
        m2 = n - (k0 + kb)
        # 尾随 DGEMM: 2*kb*m2^2
        if m2 > 0:
            dgemm_flops += 2.0 * kb * m2 * m2
            panel_flops += 2.0 * kb * m2      # panel_lu 面板列秩-1（标量）
            panel_flops += kb * kb * m2       # U12 前代（标量 axpy）
            panel_flops += 2.0 * kb * m2      # L21 打包拷贝（标量）
        k0 += kb
    solve_flops = 2.0 * n * n                  # 三角求解 + 残差（标量）

    dg = model_rvv_dgemm(int(round((dgemm_flops / 2) ** (1 / 3))),  # 等效方阵规模
                         int(round((dgemm_flops / 2) ** (1 / 3))),
                         int(round((dgemm_flops / 2) ** (1 / 3))), kp, mc)
    dgemm_cycles = dg.cycles * (dgemm_flops / max(dg.flops, 1.0))
    panel_cycles = panel_flops / mc.cores      # 标量 ~1 FLOP/cycle
    solve_cycles = solve_flops / mc.cores
    cycles = dgemm_cycles + panel_cycles + solve_cycles
    flops = 2.0 / 3.0 * n ** 3 + 2.0 * n ** 2
    peak = mc.peak_flops_per_cycle * mc.freq_ghz
    gflops = flops / cycles * mc.freq_ghz
    dgm_share = dgemm_cycles / cycles
    return ModelResult(cycles=cycles, flops=flops, gflops=gflops, peak_gflops=peak,
                       utilization=gflops / peak if peak > 0 else 0.0,
                       breakdown={"dgemm_cycles": dgemm_cycles,
                                  "panel_cycles": panel_cycles,
                                  "solve_cycles": solve_cycles,
                                  "dgemm_share": dgm_share},
                       note=f"n={n},nb={nb},mr={kp.mr},lmul={kp.lmul}")


# ---------------- 自检: 论文校准点 ----------------
if __name__ == "__main__":
    print("=== 模型自检 (对照 Ara2 论文数据) ===")
    for lanes, freq in [(2, 1.35), (4, 1.35), (8, 1.35), (16, 1.08)]:
        mc = Ara2Config(lanes=lanes, freq_ghz=freq)
        kp = KernelParams(mr=8, lmul=2, kc=128)
        r = model_rvv_dgemm(256, 256, 256, kp, mc)
        print(f"L={lanes:2d} VLEN={mc.vlen:6d}b peak={r.peak_gflops:6.2f} GFLOPS@{freq}GHz"
              f"  model={r.gflops:6.2f} GFLOPS ({r.utilization*100:5.1f}% of peak,"
              f" bound={r.breakdown['bound']})")
    # 论文: fmatmul64 (FP64 64x64) 达到理论值的 94%; 32x32 达到 76%
    for n, paper in [(32, 0.76), (64, 0.94)]:
        mc = Ara2Config(lanes=16, freq_ghz=1.0)
        kp = KernelParams(mr=4, lmul=1, kc=n)
        r = model_rvv_dgemm(n, n, n, kp, mc)
        print(f"fmatmul{n}x{n} L=16: model util={r.utilization*100:.1f}% "
              f"(论文 {paper*100:.0f}%), bound={r.breakdown['bound']}")
    # 多核对比: 8x2 vs 1x16 (论文: 8x2 在 32x32x32 上好 3 倍以上)
    mc = Ara2Config(freq_ghz=1.0)
    kp32 = KernelParams(mr=4, lmul=1, kc=32)
    r1 = model_multicore(32, 32, 32, kp32, 16, Ara2Config(lanes=16))
    r2 = model_multicore(32, 32, 32, kp32, 16, Ara2Config(lanes=2))
    print(f"32x32x32: 1x16lane={r1.gflops:.2f} GF  8x2lane={r2.gflops:.2f} GF "
          f"(论文: 多核优 3x+)")
