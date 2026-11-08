# Official HPL 2.3 validation track

This directory keeps the **official HPL 2.3** workflow separate from our
custom Linpack-style RVV workload. The upstream algorithm sources in
`third_party/hpl-2.3/` are unmodified; only build configurations and generated
objects are added. See [PROVENANCE.md](PROVENANCE.md) for the source URL and
archive hash.

## Current status

The official upstream `xhpl` has been built and run on local x86_64 WSL using
OpenMPI 4.1.6 and on the CanMV-K230 using a static RISC-V MPICH/reference BLAS
build. The x86_64 runs are workflow checks, not K230 performance claims.

| Platform | MPI ranks | N | NB | P×Q | Time (s) | GFLOPS | Scaled residual | Official result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| local x86_64 | 1 | 1000 | 128 | 1×1 | 0.15 | 4.4380 | 7.94584678e-03 | PASSED |
| local x86_64 | 2 | 1024 | 128 | 1×2 | 0.10 | 7.1378 | 5.61442609e-03 | PASSED |
| CanMV-K230 C908, one Linux CPU | 1 | 1000 | 128 | 1×1 | 3.22 | 0.20729 | 6.05923578e-03 | PASSED |
| CanMV-K230 C908, OpenBLAS ZVL128B | 1 | 1000 | 128 | 1×1 | 0.50 | 1.3239 | 9.77627218e-03 | PASSED |
| CanMV-K230 C908, OpenBLAS ZVL128B | 1 | 4096 | 128 | 1×1 | 26.35 | 1.7394 | 5.40209953e-03 | PASSED |
| CanMV-K230 C908, OpenBLAS ZVL128B | 1 | 4096 | 256 | 1×1 | 25.84 | **1.7736** | 5.13885196e-03 | PASSED |
| CanMV-K230 C908, OpenBLAS ZVL128B | 1 | 8192 | 256 | 1×1 | 194.50 | **1.8848** | 5.61038013e-03 | PASSED |
| CanMV-K230 C908, OpenBLAS ZVL128B | 1 | 8192 | 512 | 1×1 | 194.70 | 1.8829 | 5.75177252e-03 | PASSED |

Full outputs are in `results/local_np1_openmpi.log`,
`results/local_np2_openmpi.log`, `results/k230_np1_mpich.log`, and all
`results/k230_np1_openblas*.log` files. Every K230 log ends with the official
`1 tests completed and passed residual checks` and
`0 tests completed and failed residual checks` lines. Raw serial transcripts
are retained alongside the decoded logs.

The current K230 image exposes only `cpu0`; these are single-rank/single-CPU
results, not dual-core measurements. The reference BLAS row establishes an
official correctness baseline. At the same N=1000/NB=128 configuration,
OpenBLAS 0.3.34 with its RVV ZVL128B kernels improves throughput from 0.20729
to 1.3239 GFLOPS (6.39×). Three additional N=4096/NB=256 repeats measured
1.7737/1.7755/1.7857 GFLOPS (median 1.7755), all PASSED. A separate single-run
N=8192/NB=256 measurement reaches 1.8848 GFLOPS; a separate N=8192/NB=512 run
reaches 1.8829 GFLOPS. Both are single runs, so their 0.10% difference is not a
tuning ranking with established repeatability. None of these results is
presented as a TOP500-class or dual-core peak claim.

## Local build and validation

Ubuntu/Debian dependencies:

```bash
sudo apt install openmpi-bin libopenmpi-dev libblas-dev
```

Build the unmodified upstream source and run both smoke tests:

```bash
MPICC=mpicc.openmpi bash hpl/scripts/build_hpl.sh local
MPICC=mpicc.openmpi MPIRUN=mpirun.openmpi \
  bash hpl/scripts/run_hpl.sh local 1 hpl/HPL.single.dat
MPICC=mpicc.openmpi MPIRUN=mpirun.openmpi \
  bash hpl/scripts/run_hpl.sh local 2 hpl/HPL.dual.dat
```

When running as root with OpenMPI, add `MPIRUN_OPTS=--allow-run-as-root` to the
run commands. MPICH is also supported through `MPICC`/`MPIRUN`, but the local
WSL MPICH installation failed a minimal two-rank communicator test, so the
recorded validation uses OpenMPI.

## Static K230 cross-build and serial run

No BW/cloud instance is needed. Install a RISC-V cross toolchain, then build
reference BLAS and MPICH as described in [PROVENANCE.md](PROVENANCE.md). Set
`K230_MPI_DIR` to the MPICH install prefix and `K230_BLAS_LIB` to the resulting
`blas_LINUX.a`:

```bash
K230_MPI_DIR=/tmp/k230-hpl-cross/install \
K230_BLAS_LIB=/tmp/k230-hpl-cross/src/blas-3.12.0/blas_LINUX.a \
  bash hpl/scripts/build_hpl.sh k230cross

mkdir -p hpl/build/k230
cp third_party/hpl-2.3/bin/k230cross/xhpl hpl/build/k230/xhpl
riscv64-linux-gnu-strip hpl/build/k230/xhpl
gzip -9 -c hpl/build/k230/xhpl > hpl/build/k230/xhpl.gz
cp hpl/HPL.single.dat hpl/build/k230/HPL.dat
```

For the optimized build, compile OpenBLAS 0.3.34 with
`TARGET=RISCV64_ZVL128B`, `NO_THREADS=1`, `NO_SHARED=1`, and Clang 18 as
recorded in PROVENANCE.md, then set `K230_BLAS_LIB` to its `libopenblas.a`.
Keep the reference and OpenBLAS binaries under distinct names. The recorded
large inputs are `HPL.n4096_nb128.dat`, `HPL.n4096_nb256.dat`,
`HPL.n8192_nb256.dat`, and `HPL.n8192_nb512.dat`. The board reported 972 MiB
total RAM before the N=8192 run; that matrix alone occupies 512 MiB, so larger sizes should not be attempted
without a fresh memory-budget check.

For a CH342 console on COM3, the checked XMODEM script transfers both files,
removes XMODEM's final-block padding, and compares the board SHA-256 with the
local file. From Git Bash, keep `MSYS2_ARG_CONV_EXCL` set so `/root/...` is not
rewritten as a Windows path:

```bash
MSYS2_ARG_CONV_EXCL='*' powershell.exe -NoProfile -ExecutionPolicy Bypass \
  -File C:\\Data\\projects\\risc-v\\hpl\\scripts\\k230_upload_xmodem.ps1 \
  -FilePath C:\\Data\\projects\\risc-v\\hpl\\build\\k230\\xhpl.gz \
  -RemotePath /root/hpl/xhpl.gz -Port COM3
MSYS2_ARG_CONV_EXCL='*' powershell.exe -NoProfile -ExecutionPolicy Bypass \
  -File C:\\Data\\projects\\risc-v\\hpl\\scripts\\k230_upload_xmodem.ps1 \
  -FilePath C:\\Data\\projects\\risc-v\\hpl\\build\\k230\\HPL.dat \
  -RemotePath /root/hpl/HPL.dat -Port COM3
```

A successful transfer prints `TRANSFER_VERIFIED`, not merely `upload complete`.
Then unpack and run one rank on the board:

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass \
  -File C:\\Data\\projects\\risc-v\\hpl\\scripts\\k230_serial.ps1 \
  -Port COM3 -TimeoutSec 300 \
  -Command 'cd /root/hpl && gzip -d xhpl.gz && chmod 755 xhpl && ./xhpl > hpl.log 2>&1 && cat hpl.log'
```

Only record the run if the official output contains both the one-passed and
zero-failed lines. The uploaded `HPL.dat` is the N=1000, NB=128, P=Q=1 smoke
test, not a tuned maximum-memory HPL configuration.

## Optional native K230 build and run

No BW/cloud instance is needed. Run these commands on the K230 Linux system
with an MPI compiler and Fortran BLAS development library installed:

```bash
bash hpl/scripts/build_hpl.sh k230
bash hpl/scripts/run_hpl.sh k230 1 hpl/HPL.single.dat
bash hpl/scripts/run_hpl.sh k230 2 hpl/HPL.dual.dat
```

The K230 build defaults to `-O3 -march=rv64gcv -mabi=lp64d`. To select
OpenBLAS instead of the reference BLAS, set `HPL_BLAS_LIBS=-lopenblas` for both
build and run commands. Compiler flags can be overridden with `HPL_CFLAGS`.

`HPL.single.dat` and `HPL.dual.dat` are small correctness smoke tests. After
they pass, larger N and NB tuning runs are required before quoting K230 HPL
performance. Each run saves the exact input, binary/input hashes, linked
libraries, environment and complete official output under `hpl/results/`.

## Reporting boundary

- Official HPL results may only be quoted from the official `xhpl` output.
- Our existing Ara2 bare-metal program remains a custom Linpack-style workload.
- Local x86_64 results above validate the workflow and must not be presented as
  RISC-V or K230 measurements.
