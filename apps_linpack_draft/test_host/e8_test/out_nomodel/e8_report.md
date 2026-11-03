# E8 — 模型 vs RTL 实测 误差分析

- 模型: **未找到**(仅输出实测表;用 --model 指定 ara2_model.py)
- 实测行数: RTL 7 + E7 3,fmatmul 行 7

## E0 论文锚点(官方 fmatmul,16 lanes)

| s | 实测 util% | 论文 util% | Δ(pp) | 实测 cycles | FLOP/cycle |
|---|---|---|---|---|---|
| 32 | 70.10 | 76 | -5.9 | 2922 | 22.43 |
| 64 | 88.30 | 94 | -5.7 | 18555 | 28.26 |

模型自身的锚点输出(model_rvv_dgemm, mr=4/lmul=1/kc=s, L=16):
| s | 模型 util% | 论文 util% |
|---|---|---|

## 逐行误差(全部来源)

| 来源 | config | tag | 变体 | N | 实测cyc | 模型cyc | 周期误差% | 实测util% | 模型util% | Δutil pp | 模型瓶颈 | flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rtl | 16_lanes | - | v2_autovec | 256 | 2306867 | - | - | 45.45 | - | - | - | no_model |
| rtl | 16_lanes | - | rvv[8,2,128,p0] | 256 | 1363149 | - | - | 76.92 | - | - | - | no_model |
| rtl | 4_lanes | - | v0_scalar | 128 | 4529848 | - | - | 11.57 | - | - | - | no_model |
| rtl | 4_lanes | - | v2_autovec | 256 | 10066330 | - | - | 41.67 | - | - | - | no_model |
| rtl | 4_lanes | - | rvv[8,2,128,p0] | 256 | 2726298 | - | - | 153.85 | - | - | - | no_model |
| rtl | 4_lanes | - | linpack,nb=64 | 512 | 20334192 | - | - | 55.33 | - | - | - | no_model |
| rtl | 4_lanes | - | linpack,nb=32 | 512 | 18882560 | - | - | 59.58 | - | - | - | no_model |
| e7 | - | clang-O3-fast-vec | v2_autovec | 256 | 9898557 | - | - | 42.37 | - | - | - | no_model |
| e7 | - | clang-O3-novec | v2_autovec | 256 | 31876710 | - | - | 13.16 | - | - | - | no_model |
| e7 | - | gcc-O3-fast-vec | rvv[8,2,128,p0] | 256 | 3774874 | - | - | 111.11 | - | - | - | no_model |

## 按变体汇总

| 变体 | 行数 | 平均\|周期误差\|% | 最大\|周期误差\|% | 模型高估行数 | model_ceiling 行数 |
|---|---|---|---|---|---|

## 自动发现(供报告引用)


## 口径说明

- 周期对比与频率无关(双方都用 mcycle 实测周期/模型周期);util 两侧同为 fpcyc/(2×lanes),初稿 E4 换频率不改 cycles 的问题在此规避
- rvv 行的模型调用假定 k_unroll=2(模型默认;可用 E7 dump 实测修正)
- E7 novec 组的 v2 映射到标量模型(分块标量内核,近似),已打 approx 标
- linpack 实测 ROI = blocked_lu+lu_solve(不含残差计算);模型 solve 项含残差 flops,~2N² 量级,N≥512 时影响 <2%
- err% 为正 = 模型高估周期(即低估性能)
