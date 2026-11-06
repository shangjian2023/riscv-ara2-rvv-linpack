# E8 — 模型 vs RTL 实测 误差分析

- 模型: /mnt/c/Data/projects/risc-v/teammate_draft/riscv/linpack-ara2/sim/ara2_model.py
- 实测行数: RTL 57 + E7 0,fmatmul 行 20

## E0 论文锚点(官方 fmatmul,16 lanes)

| s | 实测 util% | 论文 util% | Δ(pp) | 实测 cycles | FLOP/cycle |
|---|---|---|---|---|---|
| 32 | 24.29 | 76 | -51.7 | 8433 | 7.77 |
| 64 | 47.11 | 94 | -46.9 | 34778 | 15.08 |

模型自身的锚点输出(model_rvv_dgemm, mr=4/lmul=1/kc=s, L=16):
| s | 模型 util% | 论文 util% |
|---|---|---|
| 32 | 30.2 | 76 |
| 64 | 61.5 | 94 |

## 逐行误差(全部来源)

| 来源 | config | tag | 变体 | N | 实测cyc | 模型cyc | 周期误差% | 实测util% | 模型util% | Δutil pp | 模型瓶颈 | flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rtl | 16_lanes | - | rvv[4,1,128,p0] | 256 | 2504287 | 1048576 | -58.1 | 41.87 | 100.00 | +58.13 | fpu | model_ceiling;big_err |
| rtl | 16_lanes | - | rvv[4,4,128,p0] | 256 | 2541242 | 1048576 | -58.7 | 41.26 | 100.00 | +58.74 | fpu | model_ceiling;big_err |
| rtl | 16_lanes | - | rvv[8,2,128,p0] | 256 | 2620838 | 1048576 | -60.0 | 40.01 | 100.00 | +59.99 | fpu | model_ceiling;big_err |
| rtl | 16_lanes | - | rvv[8,2,128,p1] | 256 | 2631389 | 1048576 | -60.2 | 39.85 | 100.00 | +60.15 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[16,1,128,p0] | 256 | 20593004 | 8388608 | -59.3 | 40.74 | 100.00 | +59.26 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[16,1,128,p1] | 256 | 20652862 | 8388608 | -59.4 | 40.62 | 100.00 | +59.38 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[16,2,128,p0] | 256 | 19615191 | 8912896 | -54.6 | 42.77 | 94.12 | +51.35 | fpu | big_err |
| rtl | 2_lanes | - | rvv[16,2,128,p1] | 256 | 20463641 | 8912896 | -56.4 | 40.99 | 94.12 | +53.13 | fpu | big_err |
| rtl | 2_lanes | - | rvv[2,1,128,p0] | 256 | 24188001 | 8650752 | -64.2 | 34.68 | 96.97 | +62.29 | vlsu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[2,1,128,p1] | 256 | 24205431 | 8650752 | -64.3 | 34.66 | 96.97 | +62.31 | vlsu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[2,2,128,p0] | 256 | 18476384 | 8650752 | -53.2 | 45.4 | 96.97 | +51.57 | vlsu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[2,2,128,p1] | 256 | 18492349 | 8650752 | -53.2 | 45.36 | 96.97 | +51.61 | vlsu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[2,4,128,p0] | 256 | 15628000 | 8650752 | -44.6 | 53.68 | 96.97 | +43.29 | vlsu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[2,4,128,p1] | 256 | 15645912 | 8650752 | -44.7 | 53.62 | 96.97 | +43.35 | vlsu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[2,8,128,p0] | 256 | 14202318 | 8650752 | -39.1 | 59.07 | 96.97 | +37.90 | vlsu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[2,8,128,p1] | 256 | 14230824 | 8650752 | -39.2 | 58.95 | 96.97 | +38.02 | vlsu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[4,1,128,p0] | 256 | 21043330 | 8388608 | -60.1 | 39.86 | 100.00 | +60.14 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[4,1,128,p1] | 256 | 20728753 | 8388608 | -59.5 | 40.47 | 100.00 | +59.53 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[4,2,128,p0] | 256 | 15808137 | 8388608 | -46.9 | 53.07 | 100.00 | +46.93 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[4,2,128,p1] | 256 | 15776938 | 8388608 | -46.8 | 53.17 | 100.00 | +46.83 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[4,4,128,p0] | 256 | 13136095 | 8388608 | -36.1 | 63.86 | 100.00 | +36.14 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[4,4,128,p1] | 256 | 13173531 | 8388608 | -36.3 | 63.68 | 100.00 | +36.32 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[4,8,128,p0] | 256 | 27894055 | 9699328 | -65.2 | 30.07 | 86.49 | +56.42 | fpu | big_err |
| rtl | 2_lanes | - | rvv[4,8,128,p1] | 256 | 30786693 | 9699328 | -68.5 | 27.25 | 86.49 | +59.24 | fpu | big_err |
| rtl | 2_lanes | - | rvv[8,1,128,p0] | 256 | 20326516 | 8388608 | -58.7 | 41.27 | 100.00 | +58.73 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[8,1,128,p1] | 256 | 20394270 | 8388608 | -58.9 | 41.13 | 100.00 | +58.87 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[8,2,128,p0] | 256 | 15006625 | 8388608 | -44.1 | 55.9 | 100.00 | +44.10 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[8,2,128,p1] | 256 | 15030204 | 8388608 | -44.2 | 55.81 | 100.00 | +44.19 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | - | rvv[8,4,128,p0] | 256 | 20466492 | 9175040 | -55.2 | 40.99 | 91.43 | +50.44 | fpu | big_err |
| rtl | 2_lanes | - | rvv[8,4,128,p1] | 256 | 21860850 | 9175040 | -58.0 | 38.37 | 91.43 | +53.06 | fpu | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O2-fast-vec | rvv[4,1,64,p0] | 132 | 3102980 | 1149984 | -62.9 | 37.06 | 100.00 | +62.94 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O2-fast-vec | rvv[8,2,128,p0] | 132 | 2118830 | 1222848 | -42.3 | 54.27 | 94.04 | +39.77 | fpu | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O2-fast-vec | v0_scalar | 128 | 28861899 | 4194304 | -85.5 | 3.63 | 25.00 | +21.37 | scalar-issue | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O2-fast-vec | v2_autovec | 132 | 10405074 | 2787840 | -73.2 | 11.05 | 41.25 | +30.20 | vlsu | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O2-novec | rvv[4,1,64,p0] | 132 | 3102960 | 1149984 | -62.9 | 37.06 | 100.00 | +62.94 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O2-novec | rvv[8,2,128,p0] | 132 | 2118900 | 1222848 | -42.3 | 54.27 | 94.04 | +39.77 | fpu | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O2-novec | v0_scalar | 128 | 28896044 | 4194304 | -85.5 | 3.63 | 25.00 | +21.37 | scalar-issue | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O2-novec | v2_autovec | 132 | 10404979 | 2787840 | -73.2 | 11.05 | 41.25 | +30.20 | vlsu | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O3-fast-vec | rvv[4,1,64,p0] | 132 | 2679235 | 1149984 | -57.1 | 42.92 | 100.00 | +57.08 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O3-fast-vec | rvv[8,2,128,p0] | 132 | 1975562 | 1222848 | -38.1 | 58.21 | 94.04 | +35.83 | fpu | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O3-fast-vec | v0_scalar | 128 | 28894162 | 4194304 | -85.5 | 3.63 | 25.00 | +21.37 | scalar-issue | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O3-fast-vec | v2_autovec | 132 | 10405179 | 2787840 | -73.2 | 11.05 | 41.25 | +30.20 | vlsu | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O3-novec | rvv[4,1,64,p0] | 132 | 2733845 | 1149984 | -57.9 | 42.06 | 100.00 | +57.94 | fpu | model_ceiling;big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O3-novec | rvv[8,2,128,p0] | 132 | 2001296 | 1222848 | -38.9 | 57.46 | 94.04 | +36.58 | fpu | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O3-novec | v0_scalar | 128 | 28861685 | 4194304 | -85.5 | 3.63 | 25.00 | +21.37 | scalar-issue | big_err |
| rtl | 2_lanes | e7_2_lanes_gcc-O3-novec | v2_autovec | 132 | 10405025 | 2787840 | -73.2 | 11.05 | 41.25 | +30.20 | vlsu | big_err |
| rtl | 4_lanes | - | rvv[16,2,128,p0] | 256 | 9961530 | 4456448 | -55.3 | 42.11 | 94.12 | +52.01 | fpu | big_err |
| rtl | 4_lanes | - | rvv[2,1,128,p0] | 256 | 12189244 | 4325376 | -64.5 | 34.41 | 96.97 | +62.56 | vlsu | model_ceiling;big_err |
| rtl | 4_lanes | - | rvv[4,1,128,p0] | 256 | 10487145 | 4194304 | -60.0 | 39.99 | 100.00 | +60.01 | fpu | model_ceiling;big_err |
| rtl | 4_lanes | - | rvv[4,4,128,p0] | 256 | 6548340 | 4194304 | -35.9 | 64.05 | 100.00 | +35.95 | fpu | model_ceiling;big_err |
| rtl | 4_lanes | - | rvv[8,2,128,p0] | 256 | 7636279 | 4194304 | -45.1 | 54.93 | 100.00 | +45.07 | fpu | model_ceiling;big_err |
| rtl | 4_lanes | - | rvv[8,2,128,p1] | 256 | 7651165 | 4194304 | -45.2 | 54.82 | 100.00 | +45.18 | fpu | model_ceiling;big_err |
| rtl | 4_lanes | - | rvv[8,4,128,p0] | 256 | 10386072 | 4587520 | -55.8 | 40.38 | 91.43 | +51.05 | fpu | big_err |
| rtl | 8_lanes | - | rvv[4,1,128,p0] | 256 | 5154256 | 2097152 | -59.3 | 40.69 | 100.00 | +59.31 | fpu | model_ceiling;big_err |
| rtl | 8_lanes | - | rvv[4,4,128,p0] | 256 | 3868193 | 2097152 | -45.8 | 54.22 | 100.00 | +45.78 | fpu | model_ceiling;big_err |
| rtl | 8_lanes | - | rvv[8,2,128,p0] | 256 | 3817756 | 2097152 | -45.1 | 54.93 | 100.00 | +45.07 | fpu | model_ceiling;big_err |
| rtl | 8_lanes | - | rvv[8,2,128,p1] | 256 | 3828018 | 2097152 | -45.2 | 54.78 | 100.00 | +45.22 | fpu | model_ceiling;big_err |

## 按变体汇总

| 变体 | 行数 | 平均\|周期误差\|% | 最大\|周期误差\|% | 模型高估行数 | model_ceiling 行数 |
|---|---|---|---|---|---|
| rvv | 49 | 52.4 | 68.5 | 0/49 | 37 |
| v0_scalar | 4 | 85.5 | 85.5 | 0/4 | 0 |
| v2_autovec | 4 | 73.2 | 73.2 | 0/4 | 0 |

## 自动发现(供报告引用)

- **模型天花板未被实测复现**:37 行模型 util≥95% 而实测 <80%(初稿报告里的『接近 100% 峰值』即此类模型产物):
  - rtl/16_lanes/ rvv[4,1,128,p0] N=256: 模型 100.00% vs 实测 41.87%
  - rtl/16_lanes/ rvv[4,4,128,p0] N=256: 模型 100.00% vs 实测 41.26%
  - rtl/16_lanes/ rvv[8,2,128,p0] N=256: 模型 100.00% vs 实测 40.01%
  - rtl/16_lanes/ rvv[8,2,128,p1] N=256: 模型 100.00% vs 实测 39.85%
  - rtl/2_lanes/ rvv[16,1,128,p0] N=256: 模型 100.00% vs 实测 40.74%
  - rtl/2_lanes/ rvv[16,1,128,p1] N=256: 模型 100.00% vs 实测 40.62%
  - rtl/2_lanes/ rvv[2,1,128,p0] N=256: 模型 96.97% vs 实测 34.68%
  - rtl/2_lanes/ rvv[2,1,128,p1] N=256: 模型 96.97% vs 实测 34.66%
- 最大周期误差: v0_scalar N=128 (rtl/2_lanes/e7_2_lanes_gcc-O2-fast-vec): -85.5% (模型 4194304 vs 实测 28861899 cycles)
- 各变体平均误差 — rvv: 平均|err|=52%, v0_scalar: 平均|err|=86%, v2_autovec: 平均|err|=73%

## 口径说明

- 周期对比与频率无关(双方都用 mcycle 实测周期/模型周期);util 两侧同为 fpcyc/(2×lanes),初稿 E4 换频率不改 cycles 的问题在此规避
- rvv 行的模型调用假定 k_unroll=2(模型默认;可用 E7 dump 实测修正)
- E7 novec 组的 v2 映射到标量模型(分块标量内核,近似),已打 approx 标
- linpack 实测 ROI = blocked_lu+lu_solve(不含残差计算);模型 solve 项含残差 flops,~2N² 量级,N≥512 时影响 <2%
- err% 为正 = 模型高估周期(即低估性能)
