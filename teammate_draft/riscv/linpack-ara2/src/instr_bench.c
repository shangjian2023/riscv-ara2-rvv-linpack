// instr_bench.c - instrumented build (-DINSTR_COUNT): semantic dynamic
// instruction counters vs model prediction. Define the counter globals here.
#ifdef INSTR_COUNT
unsigned long long g_ic_vec_load, g_ic_vec_store, g_ic_vec_fma, g_ic_vec_move,
    g_ic_scalar_load;
#endif

#include <riscv_vector.h>
#include "common.h"
#include "dgemm.h"

int main(void) {
#ifdef INSTR_COUNT
    const size_t N = 96, M = 80, K = 64; // exercises full blocks + all tails
    double *a = alloc_mat(N * K), *b = alloc_mat(K * M), *c = alloc_mat(N * M);
    mat_fill(a, N * K, 7);
    mat_fill(b, K * M, 9);
    for (size_t i = 0; i < N * M; i++) c[i] = 0.0;

    struct { int mr, lmul, kc, pipe; } cfgs[] = {
        {4, 1, 64, 0}, {8, 2, 64, 0}, {4, 2, 32, 0}, {8, 2, 64, 1},
    };
    printf("config,vlmax,vec_fma,vec_load,vec_store,vec_move,scalar_load\n");
    for (size_t i = 0; i < sizeof(cfgs) / sizeof(cfgs[0]); i++) {
        g_ic_vec_load = g_ic_vec_store = g_ic_vec_fma = g_ic_vec_move =
            g_ic_scalar_load = 0;
        for (size_t j = 0; j < N * M; j++) c[j] = 0.0;
        dgemm_rvv_config(cfgs[i].mr, cfgs[i].lmul, cfgs[i].kc, cfgs[i].pipe);
        dgemm_rvv(N, M, K, a, K, b, M, c, M);
        printf("mr%d_m%d_kc%d_p%d,%zu,%llu,%llu,%llu,%llu,%llu\n", cfgs[i].mr,
               cfgs[i].lmul, cfgs[i].kc, cfgs[i].pipe, __riscv_vsetvlmax_e64m1(),
               g_ic_vec_fma, g_ic_vec_load, g_ic_vec_store, g_ic_vec_move,
               g_ic_scalar_load);
    }
#else
    fprintf(stderr, "build with -DINSTR_COUNT\n");
#endif
    return 0;
}
