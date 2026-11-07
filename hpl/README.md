# Official HPL 2.3 validation track

This directory keeps the **official HPL 2.3** workflow separate from our
custom Linpack-style RVV workload. The upstream algorithm sources in
`third_party/hpl-2.3/` are unmodified; only build configurations and generated
objects are added. See [PROVENANCE.md](PROVENANCE.md) for the source URL and
archive hash.

## Current status

The official upstream `xhpl` has been built and run on local x86_64 WSL using
OpenMPI 4.1.6 and the reference BLAS. These are build/correctness checks, not
K230 performance claims.

| Platform | MPI ranks | N | NB | P×Q | GFLOPS | Scaled residual | Official result |
|---|---:|---:|---:|---:|---:|---:|---|
| local x86_64 | 1 | 1000 | 128 | 1×1 | 4.4380 | 7.94584678e-03 | PASSED |
| local x86_64 | 2 | 1024 | 128 | 1×2 | 7.1378 | 5.61442609e-03 | PASSED |

Full outputs are in `results/local_np1_openmpi.log` and
`results/local_np2_openmpi.log`. K230 board execution is still pending.

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

## Native K230 build and run

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
