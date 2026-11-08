# Official HPL 2.3 provenance

- Upstream: https://www.netlib.org/benchmark/hpl/
- Source archive: https://www.netlib.org/benchmark/hpl/hpl-2.3.tar.gz
- Release: HPL 2.3, December 2, 2018
- Downloaded: 2026-11-07
- SHA-256: `32c5c17d22330e6f2337b681aded51637fb6008d3f0eb7c277b163fadd612830`

The archive was extracted to `third_party/hpl-2.3/`. HPL algorithm sources are
kept unmodified. Only architecture configuration files named `Make.local`,
`Make.k230`, or `Make.k230cross` and generated build directories are added by
our build script. The upstream `COPYRIGHT` license and notice are retained.

## K230 static cross-build dependencies

The board binary was cross-compiled for `rv64gcv/lp64d` and statically linked
with these unmodified upstream dependencies:

| Dependency | Source archive | SHA-256 |
|---|---|---|
| Reference BLAS 3.12.0 | https://www.netlib.org/blas/blas-3.12.0.tgz | `ccc41b5d088e50db0030317ae9b0c9af375710c1392acad1fe209602da5a5aad` |
| MPICH 4.2.0 | https://www.mpich.org/static/downloads/4.2.0/mpich-4.2.0.tar.gz | `a64a66781b9e5312ad052d32689e23252f745b27ee8818ac2ac0c8209bc0b90e` |

MPICH was configured with:

```sh
./configure --host=riscv64-linux-gnu \
  --with-device=ch3:sock --with-pm=no --with-pmi=pmi1 \
  --disable-fortran --disable-cxx --disable-romio \
  --disable-shared --enable-static
```

HPL 2.3 was then built with `-O3 -march=rv64gcv -mabi=lp64d -static` using
`hpl/Make.k230cross`. The stripped board binary and its gzip archive have these
hashes:

```text
3bea88ca5cb454962ea7f6e0041de4cdaa579d365d6f9cc3943674d28ab50b5a  xhpl
4cc0ca967662fa8a41a81b580072d903f03da3407c73f86e80e5d60ba939f0f7  xhpl.gz
```

Both hashes were independently confirmed on the K230 before execution. The
board ran one MPI rank directly (no launcher), which is valid for the static
`ch3:sock` single-process build.

## Optimized RVV BLAS build

The second K230 binary links unmodified OpenBLAS 0.3.34 instead of reference
BLAS. HPL 2.3 itself remains unmodified.

- Archive: https://github.com/OpenMathLib/OpenBLAS/releases/download/v0.3.34/OpenBLAS-0.3.34.tar.gz
- SHA-256: `cd7e129868320cc2d033afa920e31202dfe0b8066a5b66661900ccc0f197dfed`
- Target: `RISCV64_ZVL128B` (RVV 1.0, 128-bit vectors)
- Build: single-threaded, static, no LAPACK/LAPACKE
- C compiler: Clang 18 with `--target=riscv64-linux-gnu --gcc-toolchain=/usr`
- OpenBLAS license: retained in the upstream `LICENSE` file

The stripped optimized HPL binary and gzip hashes are:

```text
a96481e9b7f7f1969316fb44e61668215af966c5b3e7122bef97ab8c61bf4bce  xhpl_openblas
f1c77ac8bfc6ff4f69fa3cd416213d928a977f5a5532ddd15c286f8a77b3bdb1  xhpl_openblas.gz
```

Both were verified on the board. Official HPL PASSED logs were collected at
N=1000/NB=128 and N=4096/NB=128,256. The original N=4096/NB=256 run measured
1.7736 GFLOPS with scaled residual 5.13885196e-03.

On 2026-11-08, the same N=4096/NB=256 binary and input were run three more times
on the single Linux CPU. All three official residual checks passed. The measured
rates were 1.7737, 1.7755, and 1.7857 GFLOPS (median 1.7755; times 25.84, 25.82,
and 25.67 s). The residual was 5.13885196e-03 in every run. Raw output and the
machine-checked per-repeat table are `results/k230_np1_openblas_n4096_nb256_r3.log`
and `.csv`; reproduce the table with `scripts/summarize_hpl_repeats.py`. These are
repeatability results, not a second core or a different software configuration.

A separate single run with `HPL.n8192_nb256.dat` also passed on the same board:
194.50 s, 1.8848 GFLOPS, scaled residual 5.61038013e-03. Its complete output is
`results/k230_np1_openblas_n8192_nb256.log`. The board reported 972 MiB RAM;
N=8192 uses a 512 MiB matrix before workspace. This is a single large-N data
point, not a repeated median.

Acknowledgement required by the upstream license:

> This product includes software developed at the University of Tennessee,
> Knoxville, Innovative Computing Laboratory.
