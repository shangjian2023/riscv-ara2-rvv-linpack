// Host stub: dgemm_rvv falls back to the naive kernel so the whole driver
// (check_phase -> sweep -> linpack chain) can run on x86 without RVV.
#include "lp_compat.h"
#include "dgemm.h"
void dgemm_rvv_config(int mr, int lmul, int kc, int pipeline) {
    (void)mr; (void)lmul; (void)kc; (void)pipeline;
}
int dgemm_rvv_current_mr(void)   { return 0; }
int dgemm_rvv_current_lmul(void) { return 0; }
int dgemm_rvv_current_kc(void)   { return 0; }
void dgemm_rvv(size_t n, size_t m, size_t k, const double *a, size_t lda,
               const double *b, size_t ldb, double *c, size_t ldc) {
    dgemm_naive(n, m, k, a, lda, b, ldb, c, ldc);
}
