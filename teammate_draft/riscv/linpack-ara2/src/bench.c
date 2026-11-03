// bench.c - benchmark harness: functional verification of every DGEMM variant,
// timing sweep over (MR, LMUL, PIPE) engine configs, and full Linpack runs.
// CSV goes to stdout, human-readable summary to stderr.
#include <riscv_vector.h>
#include "common.h"
#include "dgemm.h"

double linpack_run(size_t n, size_t nb, int mr, int lmul, int kc, int pipe,
                   unsigned seed, double *resid_out, double *time_out);

static void print_env(void) {
    fprintf(stderr, "RVV environment:\n");
    fprintf(stderr, "  vlmax e64m1=%zu m2=%zu m4=%zu m8=%zu\n",
            __riscv_vsetvlmax_e64m1(), __riscv_vsetvlmax_e64m2(),
            __riscv_vsetvlmax_e64m4(), __riscv_vsetvlmax_e64m8());
}

// returns max|c - ref| after computing c += a*b with the given engine config
static double check_engine(size_t n, size_t m, size_t k, int mr, int lmul, int kc,
                           int pipe, const double *a, const double *b,
                           const double *ref) {
    double *c = alloc_mat(n * m), *c0 = alloc_mat(n * m);
    for (size_t i = 0; i < n * m; i++) { c[i] = 0.5 - (double)(i % 7) * 0.1; c0[i] = c[i]; }
    dgemm_rvv_config(mr, lmul, kc, pipe);
    dgemm_rvv(n, m, k, a, k, b, m, c, m);
    dgemm_naive(n, m, k, a, k, b, m, c0, m);
    double d = max_abs_diff(c, c0, n * m);
    free(c); free(c0);
    return d;
}

int main(void) {
    print_env();
    const unsigned seed = 1234;
    const size_t N = 131, M = 126, K = 117; // odd sizes exercise all tails
    double *a = alloc_mat(N * K), *b = alloc_mat(K * M);
    mat_fill(a, N * K, seed);
    mat_fill(b, K * M, seed * 3 + 5);

    printf("section,variant,n,m,k,vlmax,mr,lmul,kc,pipe,ok,max_diff,ms,gflops\n");

    // ---- 1. functional verification ------------------------------------
    fprintf(stderr, "[check] dgemm variants on %zux%zux%zu ...\n", N, M, K);
    {
        double *cref = alloc_mat(N * M), *c1 = alloc_mat(N * M), *c2 = alloc_mat(N * M);
        for (size_t i = 0; i < N * M; i++) { cref[i] = c1[i] = c2[i] = 0.0; }
        double t0 = now_sec();
        dgemm_naive(N, M, K, a, K, b, M, cref, M);
        double t1 = now_sec();
        dgemm_blocked(N, M, K, a, K, b, M, c2, M);
        double t2 = now_sec();
        double d1 = max_abs_diff(c2, cref, N * M);
        double fl = 2.0 * N * M * K;
        printf("check,naive_scalar,%zu,%zu,%zu,%zu,0,0,0,0,1,0,%.3f,%.4f\n",
               N, M, K, __riscv_vsetvlmax_e64m1(), (t1 - t0) * 1e3, fl / (t1 - t0) / 1e9);
        printf("check,blocked_autovec,%zu,%zu,%zu,%zu,0,0,0,0,%d,%.2e,%.3f,%.4f\n",
               N, M, K, __riscv_vsetvlmax_e64m1(), d1 < 1e-9, d1, (t2 - t1) * 1e3,
               fl / (t2 - t1) / 1e9);
        free(cref); free(c1); free(c2);
    }
    // intrinsic engine: every generated (MR, LMUL, PIPE) combination
    typedef struct { int mr, lmul, pipe; } cfg3_t;
    static const cfg3_t cfgs[] = {
        {2,1,0},{2,2,0},{2,4,0},{2,8,0},{4,1,0},{4,2,0},{4,4,0},{4,8,0},
        {8,1,0},{8,2,0},{8,4,0},{16,1,0},{16,2,0},
        {2,1,1},{2,2,1},{2,4,1},{2,8,1},{4,1,1},{4,2,1},{4,4,1},{4,8,1},
        {8,1,1},{8,2,1},{8,4,1},{16,1,1},{16,2,1},
    };
    for (size_t i = 0; i < sizeof(cfgs) / sizeof(cfgs[0]); i++) {
        char name[32];
        snprintf(name, sizeof(name), "rvv_mr%d_m%d_p%d", cfgs[i].mr, cfgs[i].lmul,
                 cfgs[i].pipe);
        double d = check_engine(N, M, K, cfgs[i].mr, cfgs[i].lmul, 64, cfgs[i].pipe, a, b, NULL);
        printf("check,%s,%zu,%zu,%zu,%zu,%d,%d,64,%d,%d,%.2e,0,0\n", name, N, M, K,
               __riscv_vsetvlmax_e64m1(), cfgs[i].mr, cfgs[i].lmul, cfgs[i].pipe,
               d < 1e-9, d);
    }

    // ---- 2. engine timing sweep on a square problem ---------------------
    const size_t S = 160;
    {
        double *a2 = alloc_mat(S * S), *b2 = alloc_mat(S * S), *c2 = alloc_mat(S * S);
        mat_fill(a2, S * S, seed + 11);
        mat_fill(b2, S * S, seed + 13);
        double fl = 2.0 * S * S * S;
        static const int kcs[2] = {64, 128};
        for (size_t i = 0; i < sizeof(cfgs) / sizeof(cfgs[0]); i++) {
            for (int t = 0; t < 2; t++) {
                int kc = kcs[t];
                char name[32];
                snprintf(name, sizeof(name), "rvv_mr%d_m%d_p%d", cfgs[i].mr,
                         cfgs[i].lmul, cfgs[i].pipe);
                for (size_t j = 0; j < S * S; j++) c2[j] = 0.0;
                dgemm_rvv_config(cfgs[i].mr, cfgs[i].lmul, kc, cfgs[i].pipe);
                double t0 = now_sec();
                dgemm_rvv(S, S, S, a2, S, b2, S, c2, S);
                double t1 = now_sec();
                printf("sweep,%s,%zu,%zu,%zu,%zu,%d,%d,%d,%d,1,0,%.3f,%.4f\n", name,
                       S, S, S, __riscv_vsetvlmax_e64m1(), cfgs[i].mr, cfgs[i].lmul,
                       kc, cfgs[i].pipe, (t1 - t0) * 1e3, fl / (t1 - t0) / 1e9);
            }
        }
        free(a2); free(b2); free(c2);
    }

    // ---- 3. full Linpack -------------------------------------------------
    fprintf(stderr, "[linpack] running ...\n");
    struct { size_t n; int mr, lmul, kc, pipe; const char *tag; } lp[] = {
        {128, 4, 1, 64, 0, "baseline"},
        {128, 8, 2, 128, 0, "tuned"},
        {128, 8, 2, 128, 1, "tuned+pipe"},
        {192, 4, 1, 64, 0, "baseline"},
        {192, 8, 2, 128, 0, "tuned"},
        {192, 8, 2, 128, 1, "tuned+pipe"},
        {256, 4, 1, 64, 0, "baseline"},
        {256, 8, 2, 128, 0, "tuned"},
        {256, 8, 2, 128, 1, "tuned+pipe"},
    };
    for (size_t i = 0; i < sizeof(lp) / sizeof(lp[0]); i++) {
        double res, t;
        double g = linpack_run(lp[i].n, 32, lp[i].mr, lp[i].lmul, lp[i].kc, lp[i].pipe,
                               seed + 7 * (int)i, &res, &t);
        printf("linpack,%s,%zu,0,0,%zu,%d,%d,%d,%d,%d,%.3e,%.3f,%.4f\n", lp[i].tag,
               lp[i].n, __riscv_vsetvlmax_e64m1(), lp[i].mr, lp[i].lmul, lp[i].kc,
               lp[i].pipe, res < 100.0, res, t * 1e3, g);
        fprintf(stderr, "  linpack n=%zu %-12s resid=%.3e %.4f GFLOPS (host %.3f s)\n",
                lp[i].n, lp[i].tag, res, g, t);
    }

    free(a); free(b);
    fprintf(stderr, "done.\n");
    return 0;
}
