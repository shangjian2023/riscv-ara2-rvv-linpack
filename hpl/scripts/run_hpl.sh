#!/usr/bin/env bash
set -euo pipefail

ARCH=${1:-local}
RANKS=${2:-1}
BASE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
INPUT=${3:-$BASE/HPL.single.dat}
HPL_DIR=$(cd "$BASE/../third_party/hpl-2.3" && pwd)
XHPL="$HPL_DIR/bin/$ARCH/xhpl"
MPIRUN=${MPIRUN:-mpirun}
MPIRUN_OPTS=${MPIRUN_OPTS:-}
test -x "$XHPL"
test -f "$INPUT"
command -v "$MPIRUN" >/dev/null

RUN_DIR="$BASE/results/${ARCH}_np${RANKS}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN_DIR"
cp "$INPUT" "$RUN_DIR/HPL.dat"
sha256sum "$XHPL" "$RUN_DIR/HPL.dat" > "$RUN_DIR/SHA256SUMS"
{
  printf 'arch=%s\nranks=%s\n' "$ARCH" "$RANKS"
  printf 'mpicc=%s\n' "$(command -v "${MPICC:-mpicc}")"
  printf 'blas_libs=%s\n' "${HPL_BLAS_LIBS:--lblas}"
  uname -a
  ldd "$XHPL" || true
} > "$RUN_DIR/environment.txt"

cd "$RUN_DIR"
set +e
# MPIRUN_OPTS may intentionally contain multiple launcher arguments.
# shellcheck disable=SC2086
"$MPIRUN" $MPIRUN_OPTS -np "$RANKS" "$XHPL" 2>&1 | tee hpl.log
STATUS=${PIPESTATUS[0]}
set -e
if [[ $STATUS -ne 0 ]]; then
  printf 'HPL launcher exited with status %d\n' "$STATUS" >&2
  exit "$STATUS"
fi
grep -q '1 tests completed and passed residual checks' hpl.log
grep -q '0 tests completed and failed residual checks' hpl.log
grep -q 'PASSED' hpl.log
printf 'PASS: official HPL residual check; log: %s/hpl.log\n' "$RUN_DIR"
