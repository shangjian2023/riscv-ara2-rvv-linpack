#!/usr/bin/env bash
set -euo pipefail

ARCH=${1:-local}
case "$ARCH" in
  local)
    DEFAULT_CFLAGS="-O3 -fomit-frame-pointer -funroll-loops -Wall"
    ;;
  k230)
    DEFAULT_CFLAGS="-O3 -march=rv64gcv -mabi=lp64d -fomit-frame-pointer -funroll-loops -Wall"
    ;;
  *)
    printf 'usage: %s [local|k230]\n' "$0" >&2
    exit 2
    ;;
esac

BASE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HPL_DIR=$(cd "$BASE/../third_party/hpl-2.3" && pwd)
MPICC=${MPICC:-mpicc}
HPL_CFLAGS=${HPL_CFLAGS:-$DEFAULT_CFLAGS}
HPL_BLAS_LIBS=${HPL_BLAS_LIBS:--lblas}
command -v "$MPICC" >/dev/null
command -v make >/dev/null
cp "$BASE/Make.$ARCH" "$HPL_DIR/Make.$ARCH"

make -C "$HPL_DIR" arch="$ARCH" HPL_HOME="$HPL_DIR" \
  HPL_MPICC="$MPICC" HPL_CFLAGS="$HPL_CFLAGS" \
  HPL_BLAS_LIBS="$HPL_BLAS_LIBS" clean_arch_all >/dev/null 2>&1 || true
make -C "$HPL_DIR" arch="$ARCH" HPL_HOME="$HPL_DIR" \
  HPL_MPICC="$MPICC" HPL_CFLAGS="$HPL_CFLAGS" \
  HPL_BLAS_LIBS="$HPL_BLAS_LIBS"
printf 'Built %s/bin/%s/xhpl\n' "$HPL_DIR" "$ARCH"
