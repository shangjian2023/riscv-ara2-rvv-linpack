# E7 编译器对比 — RTL 实测汇总

## v2 自动向量化(核心对比)

| 编译/flags | v2 fpcyc | v2 cycles@N | v2 向量化? (vfmacc) | v2 vs 本组 novec | v0 fpcyc | v2/v0 加速比 |
|---|---|---|---|---|---|---|
| clang-O2-novec | 6.29 | 5400000@N=256 | no (0) | - | 3.37 | 1.87x |
| clang-O3-fast-vec | 6.90 | 4920000@N=256 | YES (1) | - | 3.37 | 2.05x |
| gcc-O2-novec | 6.30 | 5400000@N=256 | no (0) | - | 3.37 | 1.87x |
| gcc-O3-fast-vec | 6.95 | 4920000@N=256 | YES (1) | - | 3.37 | 2.06x |

## 手写内核 codegen(mr8m2, 定时 mr8m2)

| 编译/flags | mr8m2 fpcyc | util% | 总指令 | 向量指令 | sp 访问(溢出代理) |
|---|---|---|---|---|---|
| clang-O2-novec | 12.12 | 151.54 | 4 | 3 | 1 |
| clang-O3-fast-vec | 12.12 | 151.54 | 5 | 3 | 2 |
| gcc-O2-novec | 12.12 | 151.54 | 4 | 3 | 1 |
| gcc-O3-fast-vec | 12.57 | 157.16 | 7 | 3 | 4 |

## 控制项与不变量校验

- v0 标量控制 @ clang-O2-novec: OK
- v0 标量控制 @ clang-O3-fast-vec: OK
- v0 标量控制 @ gcc-O2-novec: OK
- v0 标量控制 @ gcc-O3-fast-vec: OK
- mr8m2 结果指纹跨编译器: 一致 ✓ (1 个不同值)
- v2 指纹在 vec/novec 间允许不同(浮点重结合),跨编译器 novec 组应一致

## 自动结论(供报告引用)

- v2 自动向量化最优: **gcc-O3-fast-vec** (6.95 FLOP/cycle),最差: clang-O2-novec (6.29),差距 1.11x
- 手写内核最优: **gcc-O3-fast-vec** (12.57 FLOP/cycle);各编译器 sp 访问: gcc-O3-fast-vec=4, gcc-O2-novec=1, clang-O3-fast-vec=2, clang-O2-novec=1
- 若不同编译器 sp 访问数差异大,即为『编译器寄存器分配对 VRF 溢出的影响』的直接证据(初稿只在一个编译器上看过这一点)
