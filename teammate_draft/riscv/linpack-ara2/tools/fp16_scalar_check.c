// fp16_scalar_check.c - host-side (x86) scalar validation of the split-2x2
// FP16 GEMM numerics used by the RVV kernel: verifies the ALGORITHM accuracy
// independently of ISA support (qemu 8.2 lacks zvfh execution).
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <stddef.h>

int main(void) {
    const size_t N = 96, M = 96, K = 128;
    double *a = malloc(N * K * 8), *b = malloc(K * M * 8), *cref = malloc(N * M * 8);
    unsigned seed = 4242;
    for (size_t i = 0; i < N * K; i++) {
        seed = seed * 1664525u + 1013904223u;
        a[i] = ((double)(seed >> 8) / 16777216.0 - 0.5);
    }
    for (size_t i = 0; i < K * M; i++) {
        seed = seed * 1664525u + 1013904223u;
        b[i] = ((double)(seed >> 8) / 16777216.0 - 0.5);
    }
    // fp64 reference
    for (size_t i = 0; i < N * M; i++) cref[i] = 0.0;
    for (size_t i = 0; i < N; i++)
        for (size_t l = 0; l < K; l++)
            for (size_t j = 0; j < M; j++)
                cref[i * M + j] += a[i * K + l] * b[l * M + j];

    // split-2x2 fp16 with fp32 accumulation (same math as the RVV kernel)
    double e_direct = 0.0, e_split = 0.0, norm = 0.0;
    for (size_t i = 0; i < N * M; i++)
        if (fabs(cref[i]) > norm) norm = fabs(cref[i]);
    for (size_t i = 0; i < N; i++)
        for (size_t j = 0; j < M; j++) {
            float acc_d = 0.0f, acc_s = 0.0f;
            for (size_t l = 0; l < K; l++) {
                double av = a[i * K + l], bv = b[l * M + j];
                _Float16 ah = (_Float16)av, al = (_Float16)(av - (double)ah);
                _Float16 bh = (_Float16)bv, bl = (_Float16)(bv - (double)bh);
                acc_d += (float)ah * (float)bh;
                acc_s += (float)ah * (float)bh + (float)ah * (float)bl
                       + (float)al * (float)bh;
            }
            double rd = fabs((double)acc_d - cref[i * M + j]) / norm;
            double rs = fabs((double)acc_s - cref[i * M + j]) / norm;
            if (rd > e_direct) e_direct = rd;
            if (rs > e_split) e_split = rs;
        }
    printf("N=%zu M=%zu K=%zu, |C|_inf=%.4f\n", N, M, K, norm);
    printf("fp16 direct  norm-rel err = %.3e  (~2^-11 = %.1e expected)\n",
           e_direct, ldexp(1.0, -11));
    printf("fp16 split2  norm-rel err = %.3e  (~fp32 accumulation level expected)\n",
           e_split);
    int ok = e_split < 1e-5 && e_split < e_direct * 100.0;
    printf(ok ? "SPLIT2 ACCURACY PASS\n" : "SPLIT2 ACCURACY FAIL\n");
    return !ok;
}
