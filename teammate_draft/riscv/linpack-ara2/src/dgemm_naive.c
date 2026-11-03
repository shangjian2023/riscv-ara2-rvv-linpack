// dgemm_naive.c - baseline (v0) and compiler-auto-vectorized blocked (v2) variants.
// v0 is forced to scalar codegen with per-function optimize attributes so that
// baseline and vectorized kernels live in one binary compiled with -march=rv64gcv.
#include "common.h"
#include "dgemm.h"

// v0: plain ijk triple loop, no vectorization
__attribute__((optimize("O2", "no-tree-vectorize")))
void dgemm_naive(size_t n, size_t m, size_t k, const double *a, size_t lda,
                 const double *b, size_t ldb, double *c, size_t ldc) {
    for (size_t i = 0; i < n; i++)
        for (size_t l = 0; l < k; l++) {
            double aa = a[i * lda + l];
            for (size_t j = 0; j < m; j++)
                c[i * ldc + j] += aa * b[l * ldb + j];
        }
}

// v2: cache-blocked triple loop; inner j-loop auto-vectorizes to unit-stride RVV
#define BM 64
#define BN 64
#define BK 64
__attribute__((optimize("O3", "tree-vectorize", "fast-math")))
void dgemm_blocked(size_t n, size_t m, size_t k, const double *a, size_t lda,
                   const double *b, size_t ldb, double *c, size_t ldc) {
    for (size_t ii = 0; ii < n; ii += BM) {
        size_t iie = ii + BM < n ? ii + BM : n;
        for (size_t jj = 0; jj < m; jj += BN) {
            size_t jje = jj + BN < m ? jj + BN : m;
            for (size_t ll = 0; ll < k; ll += BK) {
                size_t lle = ll + BK < k ? ll + BK : k;
                for (size_t i = ii; i < iie; i++)
                    for (size_t l = ll; l < lle; l++) {
                        double aa = a[i * lda + l];
                        for (size_t j = jj; j < jje; j++)
                            c[i * ldc + j] += aa * b[l * ldb + j];
                    }
            }
        }
    }
}
