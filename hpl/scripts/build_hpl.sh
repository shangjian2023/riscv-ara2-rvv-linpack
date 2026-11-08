#!/usr/bin/env bash
set -euo pipefail

ARCH=${1:-local}
case "$ARCH" in
  local)
    DEFAULT_CFLAGS="-O3 -fomit-frame-pointer -funroll-loops -Wall"
    DEFAULT_MPICC=mpicc
    ;;
  k230)
    DEFAULT_CFLAGS="-O3 -march=rv64gcv -mabi=lp64d -fomit-frame-pointer -funroll-loops -Wall"
    DEFAULT_MPICC=mpicc
    ;;
  k230cross)
    DEFAULT_CFLAGS="-O3 -march=rv64gcv -mabi=lp64d -fomit-frame-pointer -funroll-loops -Wall"
    DEFAULT_MPICC=riscv64-linux-gnu-gcc
    : "${K230_MPI_DIR:?set K230_MPI_DIR to the static RISC-V MPICH install prefix}"
    : "${K230_BLAS_LIB:?set K230_BLAS_LIB to the static RISC-V reference BLAS archive}"
    test -f "$K230_MPI_DIR/lib/libmpi.a"
    test -f "$K230_BLAS_LIB"
    HPL_AR=${HPL_AR:-riscv64-linux-gnu-ar}
    HPL_RANLIB=${HPL_RANLIB:-riscv64-linux-gnu-ranlib}
    ;;
  *)
    printf 'usage: %s [local|k230|k230cross]\n' "$0" >&2
    exit 2
    ;;
esac

BASE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HPL_DIR=$(cd "$BASE/../third_party/hpl-2.3" && pwd)
MPICC=${MPICC:-$DEFAULT_MPICC}
HPL_CFLAGS=${HPL_CFLAGS:-$DEFAULT_CFLAGS}
HPL_BLAS_LIBS=${HPL_BLAS_LIBS:--lblas}
HPL_AR=${HPL_AR:-ar}
HPL_RANLIB=${HPL_RANLIB:-ranlib}
command -v "$MPICC" >/dev/null
command -v "$HPL_AR" >/dev/null
command -v "$HPL_RANLIB" >/dev/null
command -v make >/dev/null
cp "$BASE/Make.$ARCH" "$HPL_DIR/Make.$ARCH"
MAKE_VARS=(
  "HPL_HOME=$HPL_DIR"
  "HPL_MPICC=$MPICC"
  "HPL_CFLAGS=$HPL_CFLAGS"
  "HPL_BLAS_LIBS=$HPL_BLAS_LIBS"
  "HPL_AR=$HPL_AR"
  "HPL_RANLIB=$HPL_RANLIB"
  "K230_MPI_DIR=${K230_MPI_DIR:-}"
  "K230_BLAS_LIB=${K230_BLAS_LIB:-}"
)

make -C "$HPL_DIR" arch="$ARCH" "${MAKE_VARS[@]}" clean_arch_all >/dev/null 2>&1 || true
make -C "$HPL_DIR" arch="$ARCH" "${MAKE_VARS[@]}"
printf 'Built %s/bin/%s/xhpl\n' "$HPL_DIR" "$ARCH"
