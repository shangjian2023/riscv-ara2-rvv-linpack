// pass_demo_main.c - functional driver for the LLVM-pass-advised binaries.
// dgemm_naive/dgemm_blocked come from either the baseline or the advised IR;
// a volatile scalar reference (vectorization-proof) provides ground truth.
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <time.h>

void dgemm_naive(size_t n, size_t m, size_t k, const double *a, size_t lda,
                 const double *b, size_t ldb, double *c, size_t ldc);
void dgemm_blocked(size_t n, size_t m, size_t k, const double *a, size_t lda,
                   const double *b, size_t ldb, double *c, size_t ldc);

static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

int main(void) {
    const size_t N = 131, M = 126, K = 117;
    double *a = malloc(N * K * 8), *b = malloc(K * M * 8);
    double *cref = malloc(N * M * 8), *c = malloc(N * M * 8);
    unsigned s = 99;
    for (size_t i = 0; i < N * K; i++) {
        s = s * 1664525u + 1013904223u;
        a[i] = (double)(s >> 8) / 16777216.0 - 0.5;
    }
    for (size_t i = 0; i < K * M; i++) {
        s = s * 1664525u + 1013904223u;
        b[i] = (double)(s >> 8) / 16777216.0 - 0.5;
    }
    // volatile scalar reference: cannot be vectorized
    for (size_t i = 0; i < N * M; i++) cref[i] = 0.0;
    for (size_t i = 0; i < N; i++)
        for (size_t l = 0; l < K; l++) {
            volatile double aa = a[i * K + l];
            for (size_t j = 0; j < M; j++) {
                volatile double bv = b[l * M + j];
                cref[i * M + j] += (double)(aa * bv);
            }
        }

    const char *names[2] = {"dgemm_naive", "dgemm_blocked"};
    void (*fns[2])(size_t, size_t, size_t, const double *, size_t, const double *,
                   size_t, double *, size_t) = {dgemm_naive, dgemm_blocked};
    for (int t = 0; t < 2; t++) {
        for (size_t i = 0; i < N * M; i++) c[i] = 0.0;
        double t0 = now_sec();
        fns[t](N, M, K, a, K, b, M, c, M);
        double t1 = now_sec();
        double err = 0.0;
        for (size_t i = 0; i < N * M; i++) {
            double e = fabs(c[i] - cref[i]);
            if (e > err) err = e;
        }
        printf("%s max_err=%.3e time=%.3fs %s\n", names[t], err, t1 - t0,
               err < 1e-9 ? "PASS" : "FAIL");
    }
    return 0;
}
