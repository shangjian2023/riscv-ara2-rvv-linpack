# apps/linpack 草案 — Ara2 裸机 Linpack/RVV 基准(RTL 实测版)

把队友初稿(`linpack-ara2`)的内核代码移植为 Ara 官方 app 形态,在
Verilator RTL 仿真下用 `mcycle` 采真实周期。**不假设频率**:输出只有
cycles / FLOP-per-cycle / %peak(峰值 = 2×NR_LANES FLOP/cycle,论文口径)。

## 文件清单与来源

| 文件 | 作用 | 相对初稿的变化 |
|---|---|---|
| `main.c` | 三阶段驱动:功能校验 / 计时扫描 / Linpack 全链路 | 新写(bench.c 的裸机版) |
| `kernel/lp_compat.h` | 裸机兼容层:LCG、尺寸宏、checksum、buffer 声明 | 替代 `src/common.h` 的宿主部分 |
| `kernel/lp_data.c` | 大缓冲区定义,`section(".l2")` 对齐 `32×NR_LANES` | 新写(替代 malloc) |
| `kernel/dgemm.h` | 变体注册表 | 原样 |
| `kernel/dgemm_naive.c` | v0 标量 / v2 自动向量化基线 | 加 clang 双路兼容 |
| `kernel/dgemm_rvv.c` | v3/v4/v5 手写 RVV 引擎,26 实例 | 仅改 include,逻辑逐行保留 |
| `kernel/linpack.c` | 分块 LU + 三角求解 + HPL 残差 | alloc→静态 buffer;计时改 `start/stop_timer`,ROI 与初稿一致(=blocked_lu+lu_solve) |

## 安装

```bash
# 假设 ara 仓库在 ~/ara(队友克隆的 work/reference/ara 即可)
cp -r linpack/ ~/ara/apps/
```

apps/Makefile 自动发现含 main.c 的目录;`data.S` 会自动 `touch` 成空文件
(输入由运行时 LCG 生成,不用大矩阵汇编)。

## 构建/运行矩阵

```bash
cd ~/ara/apps

# 常规构建(默认 lanes=4 即 config/default.mk→4_lanes.mk)
make bin/linpack

cd ../hardware
make verilate                      # 首次
app=linpack make simv              # RTL 运行,输出见下

# 换 lane 配置(E2)
app=linpack make simv config=2_lanes    # 每换 config 需重新 verilate
app=linpack make simv config=16_lanes

# 波形(E1 个案分析,只跑 tuned 内核以控制 .fst 大小)
app=linpack make simv vcd_dump=1        # 需在 apps 构建时加 ENV_DEFINES='-DVCD_DUMP=1'
cd ../apps && make bin/linpack ENV_DEFINES='-DVCD_DUMP=1' && cd ../hardware

# Ideal Dispatcher 归因(E6):标量侧不执行,只有 DGEMM 计时有效
cd ../apps && make bin/linpack.ideal
cd ../hardware && app=linpack ideal_dispatcher=1 make sim

# Spike 功能对照(交叉验证 ISA 语义)
cd ../apps && make bin/linpack.spike && make spike-run-linpack
```

### 常用构建宏(均通过 `ENV_DEFINES='-D...'` 传入)

| 宏 | 默认 | 说明 |
|---|---|---|
| `DGEMM_SWEEP_N` | 256(BIG:512) | 计时扫描的方阵规模 |
| `LINPACK_N` | 512(BIG:1024) | Linpack 规模 |
| `LINPACK_NB` | 64 | nb 上限(扫描 {32,64}) |
| `BIG` | 0 | =1 时 N 提到 1024/512,占 L2 ~23.5MB |
| `FULL_SWEEP` | 0 | =1 扫全部 26 实例(默认 6 个锚点) |
| `SWEEP_REPS` | 1 | 重复次数取最小值 |
| `SKIP_CHECK` | 0 | =1 跳过功能校验(省 RTL 时间) |
| `SKIP_SWEEP` | 0 | =1 跳过 DGEMM 计时扫描，只跑完整 Linpack 链路；CFG 标记 `mode=lp_only` |
| `SKIP_CHAIN` | 0 | =1 跳过 Linpack 链路，仅用于 DGEMM 专项实验 |
| `LP_PROFILE` | 0 | =1 增加 panel/U12/DGEMM/solve 分阶段 `PROF` 周期行 |
| `SCALAR_N` | min(N,128) | v0 标量基线规模上限 |
| `VCD_DUMP` | 0 | 波形模式:扫描只跑 (8,2,128,0) |
| `ARA_IDEAL_DGEMM_ONLY` | 0 | Ideal Dispatcher 模式:只跑 DGEMM 扫描 |

## 输出格式(机器可解析)

```
CFG,lanes=4,vlen=4096,sweepN=256,linpackN=512,nbMax=64,reps=1,mode=full
CHK,var=v2_autovec,maxdiff=0.000e+00,ref=...
CHK,var=rvv,mr=8,lmul=2,maxdiff=0.000e+00
CHECK_PHASE,PASS,fails=0
RES,phase=swp,var=v0_scalar,...,N=128,cycles=...,fpcyc=...,util=...,chk=00000000...
RES,phase=swp,var=rvv,mr=8,lmul=2,kc=128,pipe=0,N=256,cycles=...,fpcyc=...,util=...,chk=<16hex>
RES,phase=lp,var=linpack,...,N=512,nb=64,cycles=...,resid=...,chk=<16hex>
DONE,fails=0
```

- `chk` 是结果矩阵的 FNV-1a 指纹:qemu / Spike / Verilator 三平台
  **同 N 同配置必须一致**(LCG 与归约顺序逐位相同)——这是移植正确性
  的硬证据,报告里直接引用
- `util` = fpcyc / (2×NR_LANES) ×100,与初稿口径可比;但**数值来源是
  真周期**,预期不再出现 100.0% 这类模型天花板

### 本地 Linpack RTL 专项补跑

`SKIP_SWEEP=1` 只省略已完成的 DGEMM 校验和计时扫描，**不会省略 LU、
triangular solve 或残差计算**。使用现有 lane 模型时无需重新 Verilate：

```bash
# WSL；默认 4 lanes、NB=32，依次运行 mr8/m2 和 mr4/m1 两个配置
ARA_ROOT=/root/work/ara bash scripts/rtl_linpack_chain.sh 128
ARA_ROOT=/root/work/ara bash scripts/rtl_linpack_chain.sh 256

# 可选：OUT_ROOT=<独立新目录> LANES=4 NB=32
```

每个 `n<N>_nb<NB>/` 目录保存完整源码快照、编译参数、ELF/反汇编及哈希、
原始 `sim.log` 和机器解析 `res.csv`。脚本拒绝覆盖已有目录，并检查模型
lane/VLEN、`mode=lp_only`、两条 Linpack 结果、正周期、残差 `<16` 和
FLOP/cycle 重算一致性。这里的程序仍是**自研 Linpack-style 负载，不是
Netlib 官方 HPL**；计时区间仅为 `blocked_lu + lu_solve`，输入生成和残差
计算不计时。

2026-11-08 已归档首个完整 N=128/NB=32、4-lane RTL 结果：mr8/m2 为
5,708,946 cycles（0.251 FLOP/cycle，3.13%），mr4/m1 为 5,799,204 cycles
（0.247，3.08%）。两者残差均为 0.004619368，checksum 一致，
`DONE,fails=0`；wall-clock 1557.81 s。小 N 全链路效率明显低于纯 DGEMM，
该负结果不得用内核数据替代。`scripts/rtl_linpack_profile.sh` 进一步输出
`PROF` 行，测量 panel/U12/DGEMM/solve 的周期分布。

同带 profiling 的 N=128、mr8/m2 对照显示，第一轮 RVV 优化主要收益来自
panel 和 U12，而非改变 DGEMM 内核：

| 阶段 | baseline | RVV phases | panel v2 |
|---|---:|---:|---:|
| panel | 3,420,812 | 1,471,502 | 905,821 |
| U12 | 1,732,536 | 206,077 | 206,309 |
| DGEMM | 227,307 | 226,633 | 227,622 |
| solve | 322,778 | 175,968 | 175,777 |
| 总计时区间 | 5,714,244 | 2,091,060 | **1,526,260** |

RVV phases 和 panel v2 相对同带 profiling baseline 分别为 **2.73×** 和
**3.74×**；panel v2 达到 0.938 FLOP/cycle、11.72% 利用率。独立的无
profiling 对照中，RVV phases 从 5,708,946 降至 2,172,186 cycles，为
**2.63×**；panel v2 进一步降至 **1,521,378 cycles**，为 **3.75×**、
0.941 FLOP/cycle、11.76% 利用率。所有版本残差和 checksum 完全一致。

N=256、NB=32 的无 profiling 结果已完成 baseline、RVV phases 和 panel v2：
mr8/m2 分别为 25,940,413/10,005,116/7,188,195 cycles，同配置加速
**2.59×/3.61×**；panel v2 达到 1.574 FLOP/cycle、19.68% 利用率。
mr4/m1 分别为 26,856,450/10,913,579/8,143,564 cycles。所有配置和版本的
残差均为 0.004652214，checksum 完全一致；更大规模仍需独立实测。

Ara 的 `get_cycle_count()` 含 fence，profiling 会改变时序，所以 2.73×
和 3.74× 只用于同为 profiling 版本的公平对照；A21 打包等未单列开销也不能
归因到四个子项。`LP_OPT_PANEL_V2` 复用 pivot 行并向量化行交换、列缩放。
汇总键包含 `variant/profiled`，可同时保存 baseline、优化和 profiling 数据
而不会覆盖或混淆口径。

汇总和全量校验：

```bash
python3 -I scripts/summarize_local_linpack.py results/local_rtl \
  results/local_linpack_summary.csv
python3 -I scripts/validate_results.py
```

## 资源预算与仿真时长

> 下表是基于约 200kHz 的早期估算，不能作为本机wall-clock承诺。2026-11-03
> 的 4-lane 原始日志实际只有 8.045k cycles/s；主机、模型构建和程序标量部分
> 都会改变速度。专项补跑应使用 `lp_only`，并以最终日志的 cycles 和
> wallclock 统计为准。

| 配置 | L2 占用 | 估算周期 | 旧估算时长 |
|---|---|---|---|
| 默认(校验+6锚点+Linpack512) | ~6.2MB | ~35M | ~3 分钟 |
| FULL_SWEEP+BIG | ~23.5MB | ~700M | 挂一夜 |
| 单点 N=512 DGEMM(v4) | — | ~34M | ~3 分钟 |
| Linpack N=1024(BIG) | — | ~180M | ~15 分钟 |

## 已知注意事项

1. **clang 是 Ara 裸机默认编译器**(runtime.mk),v0/v2 的强制标量/
   fast-math 用了 `#pragma clang fp reassociate(on)` + `vectorize` 编译指示,
   GCC 路径保留原 `__attribute__((optimize))`。首次构建后请反汇编确认
   v2 里有 vfmacc(编译器差异本身就是实验 E7)
2. `.l2` 大数组不初始化(NOBITS);若加载流程出现脏数据,给数组加
   `= {}` 使其入 .data(见 lp_data.c 注释)
3. Ideal Dispatcher 模式下**结果无意义**(标量打包未执行),只有计时
   有效——这是设计使然,README 与报告都要写清
4. `SCALAR_N` 上限 128 是 RTL 时间预算考虑:全尺寸 v0 在仿真里要跑
   33M 周期;qemu/Spike 上想跑全尺寸可 `-DSCALAR_N=256`
5. 与宿主回归的交叉验证:初稿仓库的同 LCG/同归约顺序代码应产出相同
   checksum——给宿主 bench.c 加同样的 `lp_checksum` 打印即可对表
   (TODO,10 行)

## 下一步(对应 rtl_experiment_plan.md)

- [x] E0/E1 收集脚本:`scripts/rtl_collect.sh`(见下)
- [x] E8 模型对比:`scripts/e8_compare.py`(见下)
- [ ] E2-E5 矩阵:RTLC_CONFIGS/RTLC_LINPACK_DEFINES 组合重跑 rtl_collect.sh
- [ ] 图表脚本复用初稿 `sim/charts.py`(数据源列加 `rtl`)
- [ ] 上游 PR:本目录整理后提给 pulp-platform/ara

## E0/E1 收集 + E8 模型对比(rtl_collect.sh + e8_compare.py,已单测)

```bash
# WSL,先完成 make checkout/apply-patches/toolchain/verilate
cd <ara>/apps && bash <draft>/scripts/rtl_collect.sh
RTLC_CONFIGS="2_lanes 4_lanes 8_lanes 16_lanes" bash <draft>/scripts/rtl_collect.sh  # E2
RTLC_LINPACK_DEFINES="-DFULL_SWEEP=1" bash <draft>/scripts/rtl_collect.sh           # E3

# 单独跑 E8 对比(rtl_collect.sh 结束时也会自动调用一次)
python3 <draft>/scripts/e8_compare.py --rtl-dir <ara>/results/rtl \
    --e7-dir <ara>/results/e7 \
    --model <linpack-ara2>/sim/ara2_model.py     # 或设 ARA2_MODEL 环境变量
```

rtl_collect.sh 每个 config 做三件事:① 分别以 `def_args_fmatmul="32 32 32"` 和
`"64 64 64"` 两次构建官方 fmatmul 并运行(带 data.S 时官方 app 单点跑 s==M
且必带 `Passed.` 校验,恰好覆盖论文两个锚点尺寸);② 默认模式构建 linpack;
③ 两个 app 上 RTL 采周期,归档 log 并解析进 `results/rtl/rtl_all.csv`
+ `<config>/res.csv`。**换 config 不会自动触发 re-verilate**(make 只比较
config.mk 与模型的时间戳,旧模型显得"最新")——脚本会 touch config.mk 强制
重建,并用 `build/verilator/.ara_verilate_stamp` 记录上次配置避免重复
verilate;`data.S` 规则是 PHONY 的,def_args 覆盖不会留下陈旧数据文件。

e8_compare.py 把实测行与初稿解析模型并排(全部按周期对比,与频率无关):

| 实测变体 | 模型调用 |
|---|---|
| v0_scalar | `model_scalar_gemm` |
| v2_autovec | `model_autovec_gemm`(E7 novec 组映射标量模型,打 approx 标) |
| rvv(mr,lmul,kc,pipe) | `model_rvv_dgemm`(k_unroll 假定 2,可用 E7 dump 修正) |
| linpack(N,nb) | `model_linpack` |

产出 `e8_error.csv`(逐行 err% / Δutil / flag)+ `e8_report.md`(E0 锚点表、
逐行误差、按变体汇总、自动发现)。flag:`model_ceiling` = 模型 util≥95% 而实测
<80%(即初稿『接近 100% 峰值』那类产物)、`big_err` = |err|>30%、`approx`。

单测(host,`test_host/make_e8_fixture.py`):fixture 用**真实 ara2_model.py**
生成带已知扰动的"实测"行,校验 err 必须精确等于 −f/(1+f)——10/10 行通过,
含 model_ceiling/big_err/approx 三类 flag 触发、无模型降级路径(exit 3,
仅实测表)、rtl_collect.sh 内嵌 fmatmul 解析器(按官方 main.c 逐字格式)。
单测中已可见一个预告性事实:模型自身在论文锚点的输出(32→30.2%、64→61.5%)
与论文(76%/94%)差距很大,待真机数据确认。

## RTL 仿真实测要点(2026-11-02 调试所得,必读)

1. **仿真速度 ~8kHz 且已到顶**:实测关闭 dasm tracer、-O3 重编模型都**不提速**
   (8527 vs 8057 cycles/s,噪声内)——瓶颈是 RTL 求值本身,不是 I/O 或优化级别。
   按 8kHz×lane 数做周期预算即可(4 lane 的 linpack 默认模式 ~35M 周期 ≈ 75 分钟)
   2. **`+notrace` 需要 TB 补丁才能送达**:simctrl 与 memutil 对同一 argv 各跑一遍
   getopt,glibc 跨 pass 的置换状态把 `+notrace` 搅进 `-l` 的 optarg(报
   "meminit must be in the format..." 且与参数位置无关)。修复:`ara_tb.cpp`
   的 main 开头把 `+` 开头参数从 argv 剥离,`ParseCommandArgs` 返回后用
   `Verilated::commandArgsAdd` 补登记(`commandArgsAppend` 在 5.047 不存在)。
   关掉 tracer 的实际收益是省 ~40MB/次的 trace_hart_0.dasm(顺带保持 CWD 干净)
3. **绝不能 SIGKILL 仿真**:Verilator 缓冲 SV `$write`(UART 打印),
   进程被杀=缓冲丢失=“零输出假挂死”大乌龙(排查了一小时,实际 app 一直
   正常在跑)。要么跑完($finish 自动 flush),要么 SIGINT
   (VerilatorSimCtrl 优雅停机带统计)
3. TB L2 内存模型原默认 **1MB**(ara_tb.cpp l2_mem.size),已改 0x02000000
   (=link.ld 的 32MB);RTL 侧 tc_sram 由 L2NumWords 参数决定,足够大
4. 关键地址:退出寄存器 **0xd0000000**(写低字节=触发 $finish,
   值>>1 = tohost/退出码);**0xC0000000 = fake_uart = UART APB 窗口起始**
   (printf 的 _putchar 直写此处);sp 初值=0xC0000000(dram_end 寄存器)
5. `trace_hart_0.dasm` 是免费的逐指令提交 trace(不带 +notrace 时)——
   排查“挂死/乱跳”的第一手段,直接看最后几行
6. `.l2` 段在 GCC 下是 PROGBITS(自定义 section 的未初始化变量无法
   NOBITS),ELF 6.1MB 属正常;crt0 不清 .bss,tc_sram SimInit("random"),
   全局变量必须显式初始化
7. fmatmul 64³ 全程 272k 周期/34s(-Os 基线),`Passed.` 校验通过
   ——环境正确性的锚点

## WSL 环境实测记录(2026-11-02,Ubuntu 24.04 / 32T / 7GB)


- **GitHub 从 WSL 直连被 SNI 阻断**(github.com 000×3),codeload 可达;
  全量走 `gh-proxy.com` 镜像:`git config --global
  url."https://gh-proxy.com/https://github.com/".insteadOf ...` +
  下载 URL 前缀。PyPI 直连正常
- Verilator:仓库锁定 commit 06263ec → **5.047 devel**,`make verilator` 前需
  apt:autoconf automake libtool help2man flex bison libfl-dev g++(flex 在
  dpkg 中断中丢失过一次,报错却是 configure 失败——注意甄别)
- **编译器三件套**(E7 全矩阵可用,链接库同源公平对比):
  - xPack riscv-none-elf-gcc **15.2**(/opt/xpack/,自带 newlib;无 rv64gcv
    多库,libs 自动映射 imafdc_zicsr_zaamo_zalrsc/lp64d,ABI 兼容)
  - apt gcc-riscv64-unknown-elf 13.2(无 newlib:`-nostdlib` + 空 libm.a stub
    于 /usr/lib/riscv64-unknown-elf/lib + 自写 string.h/ctype.h shim 于
    /root/work/shim-include + `-ffreestanding`)
  - Ubuntu clang-18 + lld-18:`--target=riscv64-unknown-elf`,newlib 头/
    libm/libgcc 借 xPack 的(`-I$XPACK/riscv-none-elf/include` + 显式
    `rv64imafdc_zicsr_zaamo_zalrsc/lp64d` 档案路径)
- **GCC 构建必须整套覆盖**(e7_run.sh/rtl_collect.sh 已内置):`COMPILER=gcc`
  + `RISCV_CC_GCC` + 双 flag 变量替换 + `RUNTIME_LLVM=<gcc .o 列表>`(链接
  模板硬编码该变量!)+ `RISCV_LDFLAGS=-nostdlib -lm -lgcc ...`(否则 driver
  自动加 -lc/-lgloss 报缺库)
- 仓库从 Windows /mnt/c 拷入会**拍扁 136 个 git symlink**:先
  `git config core.symlinks true && git config core.autocrlf false &&
  git checkout -- .` 修复
- 验证:linpack ELF 两种 GCC 均构建成功(dump 中 270 条 vfmacc);v0/v2
  控制组无 fast-math 时 0 向量指令 ✓

## E7 编译器对比(scripts/e7_run.sh + e7_summarize.py,已单测)


8 组矩阵:clang/GCC × {O2,O3} × {novec, fast-math+vec},同一 Verilator 模型
采周期。main.c 的 `-DE7_MODE=1` 会自动裁剪:轻量功能门(71×66×57)+ v0/v2 +
两个手写锚点内核,无 Linpack 链路(单组合同 ~3 分钟仿真)。

```bash
# WSL,先完成 make verilate
cd <ara>/apps && bash <draft>/scripts/e7_run.sh          # 默认 4_lanes
E7_CONFIG=16_lanes bash <draft>/scripts/e7_run.sh        # 16 lane
# 产物:<ara>/results/e7/<tag>/{elf,dump,build.log,sim.log,res.csv}
#       + build_status.csv + e7_summary.csv + e7_report.md
```

实测之外,汇总器自动产出三组证据:
1. **v2 向量化触发证据**:objdump 数 `dgemm_blocked` 的 vfmacc;对比
   vec/novec 同编译器的 fpcyc 差(即"自动向量化在真实向量核上的收益")
2. **编译器对 VRF 溢出的影响**:各编译器给 mr8m2 内核的 sp 访问数
   (初稿只在 GCC 一个点看过 244/91 条,这里变成编译器维度的数据)
3. **不变量校验**:v0 必须零向量指令(否则该组控制失效剔除);
   手写内核结果指纹跨编译器必须一致

关键实现细节(改脚本前必读):
- clang 组合经 `ENV_DEFINES` 把旗标**追加在仓库默认值之后**(后旗标胜出:
  -O2 压默认 -O3,-fvectorize 压仓库的 -fno-vectorize)
- GCC 组合必须**整体替换** `RISCV_FLAGS`(仓库默认含 -mllvm/zvfh/lld,
  GCC 不认),脚本同时补回 `-DNR_LANES/-DVLEN`(从 config 名解析)
- 每组合强制清掉 app+runtime 的 .o(残留目标文件会静默污染对比)
- GCC 工具链查找顺序:repo 自建(`make toolchain-gcc`,riscv-gcc/) →
  `riscv64-unknown-elf-`(apt) → `riscv64-linux-gnu-`;apt 的 elf 包若缺
  rv64gcv multilib 会构建失败——失败会记录进 build_status.csv,本身也是
  E7 的发现("现成 GCC 工具链对 RVV 裸机的支持现状")
- summarizer 兼容 GNU/LLVM 两种 objdump 字节格式(已用合成 dump 单测)

## Host 冒烟测试(已通过,Windows/MSYS2 GCC 16 验证)

`test_host/` 提供 x86 stub(runtime 假计时 + dgemm_rvv 回退 naive),
不进 Ara 构建。用于验证驱动逻辑/缓冲区接线/LCG 数值链:

```bash
cd apps_linpack_draft
gcc -O2 -Wall -Wextra -I test_host -I linpack/kernel \
    -DDGEMM_SWEEP_N=132 -DLINPACK_N=132 \
    -o test_host/linpack_host \
    linpack/main.c linpack/kernel/lp_data.c linpack/kernel/dgemm_naive.c \
    linpack/kernel/linpack.c test_host/stub_dgemm_rvv.c -lm
./test_host/linpack_host
# 期望: CHECK_PHASE,PASS,fails=0 → DONE,fails=0
# 已验证: 14 个 rvv 配置 + v2 maxdiff=0(位精确);linpack resid=0.0057,
# 落在初稿 qemu 观测区间 [3.6e-3, 7.0e-3] → LCG/LU 数值链移植无损
```

注意:dgemm_rvv.c 真身(RVV intrinsics)只能在 riscv 工具链下编译,
host 冒烟不覆盖它——它的正确性由 qemu/Spike/RTL 三平台的 chk 对表保证
(初稿已在 qemu 验证过同一份内核代码)。
