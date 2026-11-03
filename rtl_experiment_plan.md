# RTL 实测版实验方案 — Ara2 Verilator 周期精确评测

> 项目: 面向 Linpack 的 RVV 1.0 向量编译优化(高校赛道 · 队伍"光明未来")
> 版本: v1.0 (2026-11-01)
> 定位: 取代初稿的"解析模型性能层",把全部性能结论换成 RTL 实测周期;模型降级为预测/归因工具

---

## 0. 为什么这么做(与初稿的差异)

初稿(队友版本)的致命伤:**性能数字全部来自 Python 解析公式,从未执行过 Ara2 仿真**。
本方案把"Ara2 软模拟"做实:用 Ara 官方仓库自带的 Verilator RTL 仿真跑真实周期。

初稿资产处置:
| 初稿资产 | 处置 |
|---|---|
| `src/dgemm_rvv.c` 26 内核实例 | **保留**,移植为 Ara bare-metal app |
| `src/linpack.c` 分块 LU 链路 | **保留**,同上 |
| qemu 4-VLEN 功能验证框架 | **保留**,作为快速回归 |
| objdump 指令统计/VRF 溢出分析 | **保留**,作为静态侧证据 |
| `sim/ara2_model.py` 解析模型 | **降级**为"预测工具",新角色:预测→实测→误差分析(这本身成为一个实验章节) |
| 报告/docx 管线 | **保留**,数据源全部替换 |

对照官方评分规则(归档: `competition_archive/赛题信息_高校赛道.md`):
- 技术难度与实现完整度 **30 分**:明说"**可以进行实际展示,工程源代码完整**"——RTL 实测正是"实际展示"
- 技术创新性 **25 分**:"实测校准解析模型 + 归因"比"纯模型"有说服力得多
- 应用价值 **25 分**:"提升 RISC-V 性能"需要真数据支撑
- 提交要求:第一阶段(报名截止 **11-08**)交 设计报告 + 源码 + Demo 视频(≤10min, ≤100MB, 不涉密);选拔赛/总决赛可更新迭代

---

## 1. 环境搭建(Day 1,半天~一天)

**平台**: WSL2 Ubuntu 24.04(你们已有),建议分配 8+ 核 / 32GB 内存 / 40GB 空闲磁盘。
**仓库**: 已有克隆 `work/reference/ara`(main @ 34bd3bc, 2026-08-10),直接用,不要重新克隆。

```bash
# 1) 基础依赖
sudo apt install git python3-dev python3-pip build-essential cmake flex bison libfl2 libfl-dev \
    libgoogle-perftools-dev ncurses-base libncurses5-dev libncursesw5-dev \
    device-tree-compiler libelf-dev libevent-dev util-linux
pip3 install dataclasses gitpython hjson jsonref jsonschema psutil

# 2) Bender(IP 依赖管理)
git clone https://github.com/pulp-platform/bender; cd bender && cargo install --path . # 或下载 release 二进制

# 3) RTL 依赖 checkout + 补丁(一次性)
cd hardware
make checkout
make apply-patches

# 4) Verilator(仓库锁定了 commit 06263ec,自动编译安装,约 10~20 分钟)
make verilate

# 5) 工具链(二选一,先试预编译版省时间)
#   a. 官方路线(慢,LLVM 从源码编译可能 >1 小时):
make toolchains        # 根目录 Makefile
#   b. 快速路线: 用 apt 的 riscv64-unknown-elf-gcc 13.x 先跑通,LLVM 后补
#      (apps 默认 LLVM,common/riscv_tests.mk 里 RISCV_CC 可覆盖;GCC 编译 bare-metal app 需要自带 crt0)

# 6) 冒烟测试
cd ../apps && make bin/hello_world
cd ../hardware && app=hello_world make simv
# 期望: 退出码 0,终端打印 hello world,输出含仿真周期数
```

**验收标准(Day 1 出口)**: `app=fmatmul make simv config=4_lanes` 跑通,拿到的 GFLOPS 与 Ara2 论文 fmatmul 数据同量级(64×64 FP64 ≈ 90%+ 峰值)——这一步同时就是**模型可信度的外部锚点**。

**风险与对策**:
- Verilator 编译报错(常见于 gcc 版本过新)→ 降级用 Ubuntu 22.04 容器,或 `make verilator` 换系统 verilator 5.x 手动指定
- LLVM 工具链编译太久 → 先用 GCC 路线出数据,"GCC vs LLVM 代码生成对比"反而多一个实验轴
- Bender checkout 网络问题 → 配 git 代理或 `make checkout` 重试(幂等)

---

## 2. 工程移植(Day 2,把初稿代码变成 Ara app)

Ara app 规范(参照 `apps/fmatmul/`):裸机、无 libc、数据放 `.S` 汇编文件、`runtime.h` 提供 `start_timer/stop_timer`(读 `mcycle`,RTL 下即真实周期)。

```
ara/apps/linpack/            # 新 app(上游 PR 的目标形态)
├── main.c                   # 从 bench.c 改造:去 printf→printf.h、去 malloc→静态分配
├── kernel/
│   ├── dgemm_naive.c        # 原样迁移
│   ├── dgemm_rvv.c          # 原样迁移(26 实例)
│   └── linpack.c            # alloc_mat→静态 buffer;now_sec→start/stop_timer
├── data.S                   # gen_data.py 生成(矩阵常量+校验向量)
└── script/gen_data.py       # 从初稿移植改写
```

移植要点:
1. **计时不叫 wall-clock**:每个内核/每阶段用 `HW_CNT_READY; start_timer(); ... stop_timer(); HW_CNT_NOT_READY;` 包裹,经 `printf` 输出 `{kernel, N, MR, LMUL, KC, PIPE, cycles, gflops_at_freq}`
2. **频率口径**:RTL 给的是周期数;报告 GFLOPS 一律标"@1.35GHz(论文 TT 工艺角,仅作换算)"或干脆只报 **cycles 和 %peak**——这是初稿被诟病的点,必须改
3. **矩阵规模上限**:L2 = 32MB(`L2NumWords=2^22/NrLanes` 宽字)。DGEMM N≤1024(3×8MB),Linpack N≤1024(A+a0 共 16MB + 工作区,可行)
4. 数据 `.S` 生成:沿用初稿 `frand` 的 LCG,种子写死 → qemu/Spike/RTL **三平台逐位一致**,这是强验证点
5. 保留 qemu 快速回归:同一 `kernel/` 目录,`#ifdef` 区分宿主/Ara 两套 runtime

**验收标准(Day 2 出口)**: `app=linpack make simv` N=128 全链路跑通,Linpack 残差与 qemu 一致(逐位),输出各阶段周期数。

---

## 3. 实验矩阵(Day 3~5,全部 RTL 实测周期)

仿真速度预算(Verilator 约 100~500 kHz):N=512 DGEMM ≈ 33M 周期 ≈ 分钟级;Linpack N=1024 ≈ 90M 周期 ≈ 30 分钟内。**全矩阵可在一晚跑完**,单点重跑分钟级——这是 RTL 路线可行的定量依据。

| # | 实验 | 变量 | 固定 | 直接回应初稿的什么问题 |
|---|---|---|---|---|
| **E0** | 复现锚点 | fmatmul 官方 app, N=32/64, 4/16 lane | — | 校验仿真环境正确;产出"我们 vs 论文"锚点表 |
| **E1** | 优化变体实测 | v0/v2/v3(4,1)/v4(8,2)/v5(pipe) | N=256, 4/16 lane | 初稿五个变体全是 100.0% 模型假象;实测谁高谁低见真章 |
| **E2** | lane 扩展性 | L ∈ {2,4,8,16}(`config=`) | v4, N=256 | 实测 VLEN=1024×L 结构性质;每 lane 工作量恒定的验证 |
| **E3** | MR×LMUL 扫描 | 4×4=16 组合 | N=256, 16 lane | **VRF 溢出退化(88.9%/72.7%)首次获得实测周期证据** |
| **E4** | KC 面板深度 | 32/64/128/256 | v4 | C 面板重装/卸载的真实代价(初稿模型里只有 0.125 条/k 的摊销) |
| **E5** | Linpack 全链路 | N ∈ {256,512,1024} × nb ∈ {32,64} | 最优内核 | 面板标量段/主元交换的真实占比(初稿按 1 FLOP/cyc 手拍) |
| **E6** | **Ideal Dispatcher 归因** | `ideal_dispatcher=1` vs 完整 SoC | E1/E2 子集 | **杀手锏**:官方模式把 CVA6 换成极限发射 FIFO,标量发射瓶颈 vs 向量阵列瓶颈首次可分离测量——直接检验初稿"issue-bound 61.5%"的说法 |
| **E7** | 编译器对比 | GCC vs LLVM × {-O2,-O3,-O3+fast-math} × 自动向量化 vs intrinsics | v2 内核, N=256 | 让"**编译**优化"名副其实;分数就是 RTL 周期差 |
| **E8** | 模型校准与误差分析 | 全部实测点 vs ara2_model.py 预测 | — | 把初稿最大弱点翻转为贡献:给出模型误差分布与失效边界 |

每条实验输出统一 CSV:`experiment, variant, config, N, cycles, flops, %peak, mcycle_start/end`,进 `results/`(沿用初稿目录结构,图表脚本复用)。

**波形级个案(Day 5,选做但强烈建议)**:对 E1 最优/最差内核各取一次 `trace=1`(FST),用 GTKWave 定位:向量 FMA 占空比、VLSU 排队、k 循环边界损耗。报告里放 1~2 张时序截图,评委观感完全不同。

---

## 4. 多核问题的处理(诚实口径)

Ara2 论文有多核章节,但**开源 SoC(ara_soc.sv)只集成 1×CVA6 + 1×Ara**。三个选项:
1. **基线(推荐)**:单核实测 + Ideal Dispatcher 归因,多核结论降为"基于测得单核发射参数的推演,标注未实测"
2. 进阶:Cheshire 子模块搭多簇——工作量大,仅当选拔赛阶段有余力
3. 禁止:像初稿那样把多核 3.3× 当"复现论文"写进结论(循环论证)

---

## 5. 国产平台加分项(Week 2,并行轨道)

评分标准明文"**鼓励使用国产硬件平台**"。RTL 主线之外,同一套 `kernel/` 代码(100% RVV 1.0 标准,已 4-VLEN 验证)直接上板:
- **CanMV K230(C908, RVV 1.0, VLEN 128)**:几百元,perf 硬件计数器可用
- 或 香橙派 RV2(Ky X1)
产出"开源核 RTL vs 商用核实测"对比表 → 同时喂"应用价值 25 分"和初稿列的展望。
注意 K230 是 RVV 1.0 with VLEN 128,正好落在已验证的 VLEN 可移植区间。

---

## 6. 时间表(倒排)

| 日期 | 里程碑 | 交付 |
|---|---|---|
| 11-01(今天) | 确认队长已完成报名材料提交动作;分工:你=RTL 主线,队长=qemu 回归+报告,第三人=数据脚本 | 本方案定稿 |
| 11-02 | Day1 环境搭建 + fmatmul 锚点 | 环境日志 + E0 数据 |
| 11-03 | Day2 linpack app 移植跑通 | app 截图 + 残差一致证据 |
| 11-04~05 | E1~E4(DGEMM 侧全量) | results CSV v1 |
| 11-06 | E5~E6(Linpack + Ideal Dispatcher) | 归因数据 |
| 11-07 | 报告改写(五段式模板已在 archive),数字全部换实测;E7/E8 有多少放多少;视频录制(≤10min) | **报名材料包(11-08 截止!)** |
| 11-09~27 | 预赛评审期间继续 E7/E8 + 波形分析 + 上游 PR | 选拔赛更新包(12-18 前) |

**上游 PR 计划(对应官方"附 PR/MR"要求)**:向 `pulp-platform/ara` 提交 `apps/linpack`(bare-metal Linpack benchmark + 脚本),向 Ara docs 提性能数据。哪怕只合一个小 app/文档,也是"开源贡献"实证,比零 PR 强很多。ETH PULP 收 app PR 的门槛不高(fmatmul 等就是社区贡献形态)。

---

## 7. 报告叙事重构(对照五段式)

1. **摘要**:一句话——首个面向 Ara2 开源核的 Linpack/RVV 实测评测:RTL 周期精确、覆盖 8 组实验、编译器 3 轴对比、解析模型校准
2. **背景**:RISC-V HPC 缺开源核的系统化评测;Linpack/HPL 作为标准载体(引用初稿背景段,删掉"无需开发板"的措辞——那从卖点变成了短板)
3. **方案**:实验矩阵 + 双引擎(qemu 功能 + Verilator 周期)+ 三平台一致验证
4. **创新点**(候选,按实测结果挑 3 个最强的):① 开源 RVV 核 Linpack 全链路 RTL 实测方法学;② VRF 溢出/VLEN 结构性质的实测证实;③ Ideal Dispatcher 归因;④ 模型-实测误差分析;⑤ GCC/LLVM RVV 代码生成实测对比
5. **测试总结**:全部实测表 + 波形个案 + 诚实的局限(单核、N≤1024、频率换算口径)

---

## 8. 预算与风险清单

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| Verilator/工具链编译受阻 | 中 | 卡 1-2 天 | WSL 干净环境重来;gcc 版本锁定;问 PULP GitHub issues |
| 仿真速度低于预期 | 低 | 实验矩阵缩水 | 砍 N=1024,保 N≤512;E6/E7 优先(归因和编译轴是叙事核心) |
| Linpack N=1024 内存紧张 | 中 | E5 少一个点 | a0 校验矩阵改为流式残差或降 N=768 |
| RTL 实测推翻初稿结论 | **高** | 报告叙事重写 | **这是特性不是 bug**——"实测推翻解析模型预期"本身就是结果,误差分析章节接住它 |
| 7 天内材料做不完 | 中 | 错过 11-08 | 保底包 = 初稿(qemu 功能验证完整)+ E0 锚点 + 方案章;深度内容放选拔赛更新 |
| 队友代码有隐藏 bug 移植后暴露 | 低 | 返工 | qemu 三 VLEN 回归先行,移植不改逻辑只改 runtime |

---

## 附:关键命令速查

```bash
# 配置切换(4 lane 默认;2/8/16 同理)
cd hardware && config=16_lanes make verilate && app=linpack make simv config=16_lanes

# Ideal Dispatcher 模式(E6 归因实验)
cd apps && make bin/linpack.ideal
cd hardware && app=linpack ideal_dispatcher=1 make sim

# 波形(trace=1 生成 FST,gtkwave 查看)
app=linpack make simv trace=1

# Spike 功能对照(交叉验证 ISA 语义)
cd apps && make bin/linpack.spike && make spike-run-linpack
```
