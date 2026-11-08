# K230 B-packed fair benchmark summary

DGEMM values are medians over 15/13/9/5 runs for N=160/256/512/1024.
All DGEMM outputs match the scalar reference exactly (max_diff=0).
The unpacked and packed runs are separate binaries; historical CSVs are unchanged.

| N | Scalar | GCC blocked | RVV unpacked | RVV B-packed | Packed/scalar | Packing gain |
|---:|---:|---:|---:|---:|---:|---:|
| 160 | 0.3127 | 0.2548 | 1.1363 | **1.3218** | 4.23× | 1.16× |
| 256 | 0.3057 | 0.2201 | 0.6789 | **1.1638** | 3.81× | 1.71× |
| 512 | 0.2958 | 0.1499 | 0.3047 | **0.8546** | 2.89× | 2.80× |
| 1024 | 0.2925 | 0.1271 | 0.1742 | **0.9804** | 3.35× | 5.63× |

Linpack rows use the same matrix for every variant at a given N; residuals therefore
match within each row set. These are single-run small-N custom Linpack-style results,
not official HPL scores. Official HPL 2.3 results are under `hpl/results/`.

| N | Baseline GFLOPS | mr2×m8/kc128 GFLOPS | Speedup | Shared residual |
|---:|---:|---:|---:|---:|
| 128 | 0.4000 | **0.5848** | 1.46× | 4.823e-03 |
| 192 | 0.4299 | **0.6413** | 1.49× | 4.141e-03 |
| 256 | 0.3421 | **0.5127** | 1.50× | 4.237e-03 |
