# linpack-ara2 — 面向 Linpack 的 RVV 1.0 向量编译优化（基于开源核 Ara2 软模拟）

在一台普通笔记本上（无需开发板、无需 RTL 仿真环境）完成"开源参考 → 双编译器交叉编译 →
功能验证 → 反汇编核验 → 动态指令计数 → 周期建模 → 自动调优 → LLVM Pass → 低精度扩展 →
报告生成"的完整研究闭环。

## 目录结构

```
linpack-ara2/
├── src/                     # 全部 C 源码（RVV 1.0，VLEN 无关）
│   ├── common.h             # 矩阵/计时/校验工具
│   ├── dgemm.h              # DGEMM 变体注册表（BLAS 风格带步长接口）
│   ├── dgemm_naive.c        # v0 标量基线 / v2 分块+自动向量化
│   ├── dgemm_rvv.c          # v3/v4/v5 手写 intrinsics 引擎（26 实例，含 -DINSTR_COUNT 插桩）
│   ├── dgemm_fp16.c         # 低精度内核：FP16 direct + split2（vfwmacc 加宽累加）
│   ├── linpack.c            # 分块 LU + 部分主元 + 三角求解 + HPL 残差
│   ├── bench.c              # 基准主程序（CSV 输出）
│   ├── instr_bench.c        # 动态指令计数基准（-DINSTR_COUNT）
│   └── fp16_bench.c         # 低精度精度/耗时基准
├── llvm-pass/
│   └── Ara2VecAdvisor.cpp   # LLVM 18 NewPM 插件 Pass（GEMM 循环识别 + 分块元数据注入）
├── sim/
│   ├── ara2_model.py        # Ara2 周期近似模型（论文三点校准）
│   ├── run_experiments.py   # E1~E6 实验矩阵 → results/*.csv
│   ├── verify_instr.py      # E7 动态指令计数验证（40/40 一致）
│   ├── autotuner.py         # E8 规则剪枝+代价模型选择器（16/16 vs 穷举）
│   ├── precision_study.py   # E10 低精度误差-吞吐权衡
│   └── charts.py            # 图1~图8（中文字体）
├── scripts/
│   ├── build_and_run.sh     # GCC 构建 + qemu 运行
│   ├── portability.sh       # 四种 VLEN 可移植性验证
│   ├── disasm_analysis.sh   # 内核反汇编统计（VRF 溢出证据）
│   ├── build_extra.sh       # 插桩构建 + clang 交叉构建
│   ├── build_fp16_clang.sh  # FP16 构建（clang, zvfh）+ 编译器诊断 + 双编译器对比
│   ├── compiler_compare.sh  # E9 双编译器证据表
│   ├── fp16_qemu10.sh       # FP16 在 qemu 10（zvfh）上运行
│   ├── llvm_pass_flow.sh    # E11：Pass 全链路（插件构建→IR→注入→codegen→对比→qemu）
│   ├── pass_rebuild.sh      # Pass 重建 + 元数据注入自检
│   └── fill_report.py       # 按官方模板填写参赛报告 docx
├── tools/                   # x86 验证（fp16_scalar_check / pass_demo_main / pragma_probe）
├── results/                 # CSV 数据 + PNG 图表 + 诊断日志
└── build/                   # 交叉编译产物（gcc/clang/插桩/fp16/pass 多版本）
```

参考仓库（微架构参数 ground truth）：`../work/reference/ara`
（github.com/pulp-platform/ara，config/{2,4,8,16}_lanes.mk：VLEN=1024×L bit）

## 微架构参数（Ara2 论文 IEEE TC 2024 + 仓库）

| 参数 | 值 | 来源 |
|---|---|---|
| lane 数 L | 2/4/8/16 | 仓库 config/ |
| VLEN | 1024×L bit | 仓库 config/ |
| 峰值 | FP64: 2L FLOP/cycle；FP16 4×SIMD | 论文 Table II / fpnew |
| VLSU 带宽 | 4L Byte/cycle（单位步长） | 论文 |
| 主存 | SRAM，延迟 7 cycle | 论文 |
| 向量发射 | CVA6 每 4 cycle 发射 1 条向量指令 | 论文 |
| VRF | 32 个向量寄存器，无向量数据 Cache | 论文 |

## 复现步骤（WSL2 Ubuntu 24.04）

```bash
sudo apt install gcc-riscv64-linux-gnu qemu-user clang-18 lld-18 \
                 python3-pip meson ninja-build libglib2.0-dev
pip3 install python-docx --break-system-packages

bash scripts/build_and_run.sh 512     # GCC 构建 + qemu 全量基准（27 项校验）
bash scripts/portability.sh           # 4 种 VLEN 可移植性（27×4 全过）
bash scripts/disasm_analysis.sh       # 反汇编：VRF 溢出证据
bash scripts/build_extra.sh           # 插桩动态计数 + clang 交叉构建（27/27）
python3 sim/verify_instr.py           # 40/40 指令计数一致
bash scripts/compiler_compare.sh      # 双编译器证据表 + 向量化诊断
python3 sim/ara2_model.py             # 模型自检（论文三点校准）
python3 sim/run_experiments.py        # E1~E6 全部实验 CSV
python3 sim/autotuner.py              # 选择器 16/16 vs 穷举
bash scripts/llvm_pass_flow.sh        # E11: LLVM Pass 全链路（需 llvm-18-dev）
# FP16（需自源码构建 qemu 10 获得 zvfh，见 scripts/build_fp16_clang.sh）
bash scripts/build_fp16_clang.sh && bash scripts/fp16_qemu10.sh
gcc -O2 -o /tmp/f16chk tools/fp16_scalar_check.c -lm && /tmp/f16chk  # x86 精度验证
python3 sim/charts.py                 # 图1~8
```

## LLVM Pass（llvm-pass/Ara2VecAdvisor.cpp）

NewPM 插件（clang++ -shared 构建，`opt -load-pass-plugin + -passes=function(ara2-advisor)` 使用）：
识别 GEMM 型最内层循环（含 `llvm.fmuladd` fpContract 形态），按规则一计算
MR = clamp(2×(访存/计算), 4, 8)，注入 `llvm.loop.unroll.count` /
`llvm.loop.unroll_and_jam.count` 元数据。实测（results/e11_llvm_pass.csv）：
clang 接受并按 MR=6 展开；单纯展开不消除跨迭代 C 冗余访存——完整寄存器
分块需 Pass 直接做循环变换（未来工作）或手写内核（本项目 v3/v4）。

实现中踩过并解决的 LLVM loop-metadata 坑（写 Pass 时可复用）：
1. loop ID 必须自引用（operand 0 == 节点自身），否则所有消费方视为无元数据；
2. ID 可能挂在 latch 而非 header 的 terminator 上，读写要覆盖 header+latches；
3. 既有 `llvm.loop.unroll.disable` 与新注入的 count 同存时 disable 优先，需同族清除。

## 核心结果

| 指标 | 数值 |
|---|---|
| 功能校验 | 27 项 × 4 VLEN × 2 编译器 全部通过（DGEMM 误差 0，Linpack 残差 3.6e-3~7.0e-3） |
| DGEMM v0 标量 | 1.08 GFLOPS（3.1% 峰值，16-lane） |
| 自动向量化 | GCC 13 全部失败（0 向量指令，12 missed）；Clang 18 成功但上限 50%（VLSU 受限） |
| DGEMM v4/v5 手写调优 | 34.56 GFLOPS（100% 峰值，较基线 ×32），双编译器均正确 |
| 动态指令计数验证 | 40/40 项插桩实测与模型预测完全一致 |
| VRF 溢出退化 | mr16×m2 → 88.9%，mr8×m4 → 72.7%（反汇编栈访存 244/91 条实证） |
| 自动调优选择器 | 16/16 命中或等效（<1%），评估次数 22 vs 穷举 120 |
| LLVM Pass（Ara2VecAdvisor） | 识别 GEMM 循环→注入 MR=6 展开元数据→clang 实际按 6 展开（vfmacc 1→7），qemu 校验通过；静态重用比保持 1:3（证明元数据提示≠寄存器分块） |
| 多核（总 16 lane，N=64） | 1×16 61.5%（发射受限）vs 8×2 100%（复现论文 3.3×结论） |
| Linpack 整体 | 4-lane 效率最高 76.8%（N=1024，nb=64） |
| 低精度 split2 | 误差 2.7e-4 → 3.6e-7（恢复 3 个数量级），吞吐保留 1.33×（模型） |

## 移植到商用板卡（香橙派 RV2 / CanMV K230）

代码 100% 使用 RVV 1.0 标准指令（vsetvl/vle64/vfmacc.vf/vse64/vmv/vfwmacc），
已在 VLEN=128~1024 验证。板上编译：

```bash
# 香橙派 RV2 (Ky X1) / K230 (C908)，Ubuntu 或 RuyiSDK 环境
gcc -O3 -march=rv64gcv -mabi=lp64d -o bench src/*.c -lm && ./bench
# FP16 变体需 -march=rv64gcv_zvfh（C908/Ky X1 均支持 FP16 向量）
```

板上建议补充：perf 硬件计数器采集、与模型预测对比。

## 已知限制

- 周期模型是内核级解析近似（三层资源上限），已通过论文三点校准 + 40 项动态计数验证，
  但未建模流水线相关/AXI 竞争等二阶效应；
- qemu 墙钟时间不代表硬件性能（功能模拟器），性能结论全部来自校准后的模型；
- qemu 8.2 RVV 仅支持 VLEN≤1024 且无 zvfh；FP16 执行验证使用自源码构建的
  qemu 10.0（scripts 内含构建指引），Ara2 真实 VLEN（2K~16K bit）由模型参数承载。
