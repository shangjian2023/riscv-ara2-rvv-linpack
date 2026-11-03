// pragma_probe.c - control experiment: does clang honor unroll_count pragma
// (same llvm.loop.unroll.count metadata path our pass writes) on the middle
// loop of the naive DGEMM? If the pragma works, the pass metadata plumbing
// is the issue; if not, the loop shape rejects runtime unrolling at -O2/-O3.
#include <stddef.h>
void dgemm_pragma(size_t n, size_t m, size_t k, const double *a, size_t lda,
                  const double *b, size_t ldb, double *c, size_t ldc) {
    for (size_t i = 0; i < n; i++)
#pragma clang loop unroll_count(6)
        for (size_t l = 0; l < k; l++) {
            double aa = a[i * lda + l];
            for (size_t j = 0; j < m; j++)
                c[i * ldc + j] += aa * b[l * ldb + j];
        }
}
