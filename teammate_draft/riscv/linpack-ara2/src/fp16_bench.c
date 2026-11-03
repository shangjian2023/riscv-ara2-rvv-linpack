// fp16_bench.c - low-precision DGEMM accuracy/perception study driver.
// Runs the FP64 RVV kernel as reference, then direct-FP16 and split2-FP16
// (Ozaki-lite) kernels, reporting max relative error and wall time on the
// functional simulator (qemu times are indicative only; throughput claims
// come from the Ara2 cycle model in sim/ara2_model.py).
#include <riscv_vector.h>
#include "common.h"
#include "dgemm.h"

void dgemm_f16_direct(size_t n, size_t m, size_t k, const double *a,
                      const double *b, const double *c_ref, double *rel_err_out);
void dgemm_f16_split2(size_t n, size_t m, size_t k, const double *a,
                      const double *b, const double *c_ref, double *rel_err_out);

int main(void) {
    const size_t N = 96, M = 96, K = 128;
    double *a = alloc_mat(N * K), *b = alloc_mat(K * M), *cref = alloc_mat(N * M);
    mat_fill(a, N * K, 21);
    mat_fill(b, K * M, 33);
    for (size_t i = 0; i < N * M; i++) cref[i] = 0.0;

    // FP64 RVV reference
    dgemm_rvv_config(8, 2, 128, 0);
    dgemm_rvv(N, M, K, a, K, b, M, cref, M);
    double norm = 0.0;
    for (size_t i = 0; i < N * M; i++)
        if (fabs(cref[i]) > norm) norm = fabs(cref[i]);

    double e1, e2, t0, t1;
    printf("kernel,max_rel_err,vs_fp64_time\n");
    t0 = now_sec();
    dgemm_f16_direct(N, M, K, a, b, cref, &e1);
    t1 = now_sec();
    printf("f16_direct,%.3e,%.3f\n", e1, t1 - t0);
    t0 = now_sec();
    dgemm_f16_split2(N, M, K, a, b, cref, &e2);
    t1 = now_sec();
    printf("f16_split2,%.3e,%.3f\n", e2, t1 - t0);
    fprintf(stderr, "reference |C|_inf=%.3f, elems=%zu, vlmax_e64m1=%zu\n", norm,
            N * M, __riscv_vsetvlmax_e64m1());
    fprintf(stderr, "done\n");
    return 0;
}
