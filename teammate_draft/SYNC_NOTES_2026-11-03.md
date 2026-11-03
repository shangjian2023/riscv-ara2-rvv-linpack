# 初稿（linpack-ara2）增量同步说明 — 2026-11-03

本分支把队友 `linpack-ara2` 项目的最新全流水线工作同步进 `teammate_draft/riscv/linpack-ara2/`，
替换 11-01 的旧快照。所有新增实验均有可复现脚本与数据（`results/e7~e11*.csv`）。

## 一、相对旧快照的增量

### 1. 双编译器对比（e9 / f7 / diag_*.txt）
- clang-18 交叉编译链路打通，bench 全量 27 项校验在 clang 二进制上同样全过；
- **GCC 13.3 对朴素/分块两版基线生成的向量指令数为 0**（-fopt-info-vec 报告 12 处 missed，
  证明旧 qemu 数据中 v2≈v0 的原因是 GCC 根本没向量化）；Clang 18 同源码全部向量化（2/0），
  但形态为 B 复用=1，模型评估其上限为峰值的 50%（VLSU 受限）；
- `apps_linpack_draft/kernel/dgemm_naive.c` 已有的 clang 双路兼容与该结论互证。

### 2. 动态指令计数验证（e7，`-DINSTR_COUNT` 插桩）
- `src/dgemm_rvv.c` 增加编译期插桩开关；`src/instr_bench.c` + `sim/verify_instr.py`；
- **8 组内核配置 × 5 类计数 × 2 种 VLEN 共 40 项，插桩实测与模型解析预测逐项一致（误差 0）**。
  模型指令流假设从"静态反汇编同构"升级为"运行时精确匹配"。

### 3. 规则驱动自动调优选择器（e8）
- `sim/autotuner.py`：R1/R2 剪枝 + 代价公式评估，约 22 次评估替代 120 次穷举；
- 16 个（lane, N）组合 **16/16 命中或等效（性能差 <1%）**。

### 4. LLVM 18 NewPM 插件 Pass（e11，llvm-pass/Ara2VecAdvisor.cpp）
- 识别 GEMM 型内层循环（含 fpContract 形成的 llvm.fmuladd intrinsic），按规则一计算
  MR=clamp(2×(访存/计算),4,8)，注入 `llvm.loop.unroll(_and_jam).count` 元数据；
- 全链路实测：clang 接受并按 MR=6 展开（vfmacc 1→7，函数体积 128→549 行），qemu 功能校验通过；
- **负结果**：单纯元数据展开不消除跨迭代 C 冗余访存（静态重用比保持 1:3），unroll-and-jam
  对 (k,j) 形状保守拒绝——反向论证"寄存器分块必须落在内核结构上"；
- 实现踩坑记录（自引用 loop ID / latch 挂载 / disable 冲突清除）见项目 README。

### 5. 低精度扩展：Ozaki-lite split-FP16（e10 / f8）
- `src/dgemm_fp16.c`：vfwmacc（FP16 输入 FP32 累加）direct/split2 两版内核；
- 精度：直接 FP16 归一化误差 2.7e-4（符合 2^-11 量化预期），split2 恢复至 3.6e-7（FP32 累加水平）；
- 执行验证：x86 标量 + RVV qemu 双路径（后者需自源码构建 qemu 10 以获得 zvfh，脚本已含）；
- 模型：直接 FP16 吞吐 4×FP64；split2 三遍后 1.33×（基于 fpnew 4×SIMD 结构的解析推算）。

### 6. 模型修正（影响预测对比，见下节）
- `sim/ara2_model.py` 两处 KC 摊销修正（k 尾块按实际面板深 kcq 计算，发射与 VLSU 两处）。

### 7. 其他
- 更新版参赛设计报告（docx + PDF）置于 `teammate_draft/riscv/`，五章节字数达标，8 图 5 表；
- 移除旧快照中误提交的 `build/bench` 二进制（可重建），`build/` 目录整体加入 .gitignore。

## 二、与 rtl_experiment_plan.md 的衔接点

1. **E8（模型预测 vs RTL 实测）务必使用同步后的 `sim/ara2_model.py`**：
   KC 摊销修复改变了小规模场景的预测值（如 16-lane/N=64 的最优配置预测），
   旧快照模型会引入系统性偏差。
2. **e7 的 40/40 动态计数一致**可直接写入"预测→实测→误差分析"章节：
   说明模型误差来源集中在时序参数（发射间隔/访存延迟），而非指令流结构。
3. **e9 双编译器结论**与 apps_linpack_draft 的 clang 兼容层互证；
   **e11 的负结果**可作为报告中"手写内核不可替代"的编译器层反向证据。
4. FP16 变体未来可在 RTL 上复测（Ara2 的 vmfpu 支持 FP16 4×SIMD，与模型假设一致）。

## 三、复现入口（WSL2 Ubuntu 24.04）

```bash
cd teammate_draft/riscv/linpack-ara2
bash scripts/build_and_run.sh 512        # 基线 27 项校验
bash scripts/build_extra.sh              # 插桩计数 + clang 双编译器
python3 sim/verify_instr.py              # e7: 40/40
python3 sim/autotuner.py                 # e8: 16/16
bash scripts/llvm_pass_flow.sh           # e11: LLVM Pass 全链路（需 llvm-18-dev）
bash scripts/build_fp16_clang.sh && bash scripts/fp16_qemu10.sh   # e10
```
