# 面向 RVV 1.0 的 Linpack 应用性能优化

光明未来队｜国防科技大学

本项目在 **Ara2 RTL** 与 **CanMV-K230/C908 商用板** 上验证 RVV 1.0 性能优化。自研 Linpack 求解程序与官方 **Netlib HPL 2.3** 分开构建、计时和归档。

## 已实测结果

| 平台与负载 | 对照 | 结果 |
|---|---|---|
| Ara2，128阶求解全过程，4通道/NB=32 | 基线 → 第二轮列分块优化 | 5,708,946 → 1,521,378周期，**3.75×**，11.76%利用率 |
| Ara2，256阶求解全过程，4通道/NB=32 | 基线 → 第二轮列分块优化 | 25,940,413 → 7,188,195周期，**3.61×**，19.68%利用率 |
| K230，官方HPL N=1000/NB=128 | Reference BLAS → OpenBLAS RVV | 0.20729 → 1.3239 GFLOPS，**6.39×** |
| K230，官方HPL N=8192/NB=256 | 单Linux CPU、单MPI rank，单次 | **1.8848 GFLOPS，PASSED** |

两种Ara2矩阵规模的优化前后残差与校验和一致。官方HPL原始输出均保留，K230结果不表示双核或TOP500成绩。

## 入口

- **源码包与复现说明**：[`SOURCE_PACKAGE.md`](SOURCE_PACKAGE.md)
- RVV内核、LU分解、三角求解与RTL脚本：[`apps_linpack_draft/`](apps_linpack_draft/)
- 官方HPL构建、输入与原始日志：[`hpl/`](hpl/)
- 最终报告和八组图表：`report_archive/2026-11-08/`
- Demo分镜、配音稿与视频构建脚本：[`demo/`](demo/)

## 快速校验

```bash
python -I apps_linpack_draft/scripts/validate_results.py
python -I demo/scripts/show_evidence.py
```

当前校验覆盖93条云端结果、57项理论推算对比、89条历史K230结果、496条公平矩阵乘结果、92条B矩阵打包完整结果、8份官方HPL日志、3次官方HPL重复运行和18条本地RTL求解结果。

## 核心优化

- 第一轮：连续行更新、RVV整行交换、跨步列缩放和行式前代求解。
- 第二轮：主元行驻留向量寄存器并跨下游行复用，减少列面板重复加载。
- K230：参数化矩阵乘、软件流水与B矩阵块连续布局。
- 证据链：保留配置、编译参数、原始日志、反汇编、CSV和SHA-256；分阶段计时与不计时结果分开呈现。

远程仓库：https://github.com/shangjian2023/riscv-ara2-rvv-linpack
