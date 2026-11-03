# linpack-ara2 — 面向 Linpack 的 RVV 1.0 向量编译优化（基于开源核 Ara2 软模拟）

在一台普通笔记本上（无需开发板、无需 RTL 仿真环境）完成"开源参考 → 交叉编译 →
功能验证 → 反汇编核验 → 周期建模 → 参数寻优 → 报告生成"的完整研究闭环。

## 目录结构

```
linpack-ara2/
├── src/                     # 全部 C 源码（RVV 1.0，VLEN 无关）
│   ├── common.h             # 矩阵/计时/校验工具
│   ├── dgemm.h              # DGEMM 变体注册表（BLAS 风格带步长接口）
│   ├── dgemm_naive.c        # v0 标量基线 / v2 分块+自动向量化
│   ├── dgemm_rvv.c          # v3/v4/v5 手写 intrinsics 引擎（26 个宏生成实例）
│   ├── linpack.c            # 分块 LU + 部分主元 + 三角求解 + HPL 残差
│   └── bench.c              # 基准主程序（CSV 输出）
├── sim/
│   ├── ara2_model.py        # Ara2 周期近似模型（论文三点校准）
│   ├── run_experiments.py   # E1~E6 实验矩阵 → results/*.csv
│   └── charts.py            # 图1~图6（中文字体）
├── scripts/
│   ├── build_and_run.sh     # 构建 + qemu 运行（WSL）
│   ├── portability.sh       # 四种 VLEN 可移植性验证
│   ├── disasm_analysis.sh   # 内核反汇编指令统计（VRF 溢出证据）
│   └── fill_report.py       # 按官方模板填写参赛报告 docx
├── results/                 # CSV 数据 + PNG 图表 + qemu 运行记录
└── build/                   # 交叉编译产物
```

参考仓库（微架构参数 ground truth）：`../work/reference/ara`
（github.com/pulp-platform/ara，config/{2,4,8,16}_lanes.mk：VLEN=1024×L bit）

## 微架构参数（Ara2 论文 IEEE TC 2024 + 仓库）

| 参数 | 值 | 来源 |
|---|---|---|
| lane 数 L | 2/4/8/16 | 仓库 config/ |
| VLEN | 1024×L bit | 仓库 config/ |
| 峰值 | 2L DP-FLOP/cycle（每 lane 1 FP64 FMA） | 论文 Table II |
| VLSU 带宽 | 4L Byte/cycle（单位步长） | 论文 |
| 主存 | SRAM，延迟 7 cycle | 论文 |
| 向量发射 | CVA6 每 4 cycle 发射 1 条向量指令 | 论文 |
| VRF | 32 个向量寄存器，无向量数据 Cache | 论文 |

## 复现步骤（WSL2 Ubuntu 24.04 + qemu-riscv64）

```bash
sudo apt install gcc-riscv64-linux-gnu qemu-user python3-pip
pip3 install python-docx --break-system-packages   # 仅报告生成需要

bash scripts/build_and_run.sh 512     # 构建 + qemu VLEN=512 全量基准
bash scripts/portability.sh           # 128/256/512/1024 四种 VLEN 验证
python3 sim/ara2_model.py             # 模型自检（论文三点校准）
python3 sim/run_experiments.py        # E1~E6 → results/*.csv
python3 sim/charts.py                 # 图1~6
```

## 核心结果

| 指标 | 数值 |
|---|---|
| 功能校验 | 27 项 × 4 VLEN 全部通过（DGEMM 误差 0，Linpack 残差 3.6e-3~7.0e-3） |
| DGEMM v0 标量 | 1.08 GFLOPS（3.1% 峰值，16-lane） |
| DGEMM v2 自动向量化 | 17.28 GFLOPS（50%，VLSU 受限） |
| DGEMM v4/v5 手写调优 | 34.56 GFLOPS（100% 峰值，较基线 ×32） |
| VRF 溢出退化 | mr16×m2 → 88.9%，mr8×m4 → 72.7%（反汇编栈访存 244/91 条实证） |
| 多核（总 16 lane，N=64） | 1×16 61.5%（发射受限）vs 8×2 100%（复现论文结论，3.3×） |
| Linpack 整体 | 4-lane 效率最高 76.8%（N=1024，nb=64） |

## 移植到商用板卡（香橙派 RV2 / CanMV K230）

代码 100% 使用 RVV 1.0 标准指令（vsetvl/vle64/vfmacc.vf/vse64/vmv），
已在 VLEN=128~1024 验证。板上编译：

```bash
# 香橙派 RV2 (Ky X1) / K230 (C908)，Ubuntu 或 RuyiSDK 环境
gcc -O3 -march=rv64gcv -mabi=lp64d -o bench src/*.c -lm && ./bench
```

板上建议补充：perf 硬件计数器采集、perf stat 周期与指令数、与模型预测对比。

## 已知限制

- 周期模型是内核级解析近似（三层资源上限），未建模流水线相关/AXI 竞争等二阶效应；
- qemu 墙钟时间不代表硬件性能（功能模拟器），性能结论全部来自校准后的模型；
- qemu 8.2 RVV 仅支持 VLEN≤1024，Ara2 真实 VLEN（2K~16K bit）由模型参数承载。
