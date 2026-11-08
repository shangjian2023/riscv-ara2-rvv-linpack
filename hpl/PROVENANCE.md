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

Acknowledgement required by the upstream license:

> This product includes software developed at the University of Tennessee,
> Knoxville, Innovative Computing Laboratory.
