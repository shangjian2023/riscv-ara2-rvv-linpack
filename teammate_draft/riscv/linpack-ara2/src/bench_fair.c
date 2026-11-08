// bench_fair.c - repeated, same-shape DGEMM comparison for K230/C908.
// The original bench.c compares the best RVV sweep at 160^3 with baselines at
// 131x126x117. This benchmark removes that shape confound and reports spread.
#include "common.h"
#include "dgemm.h"

typedef void (*bench_fn)(size_t, size_t, size_t, const double *, size_t,
                         const double *, size_t, double *, size_t);

typedef struct {
    const char *name;
    bench_fn fn;
    int mr, lmul, kc, pipe;
} variant_t;

static int compare_double(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static void print_summary(const char *variant, size_t n, double *times,
                          int reps, double max_diff) {
    qsort(times, (size_t)reps, sizeof(times[0]), compare_double);
    double flop = 2.0 * n * n * n;
    struct { const char *name; int index; } stats[] = {
        {"min", 0}, {"q1", reps / 4}, {"median", reps / 2},
        {"q3", (3 * reps) / 4}, {"max", reps - 1},
    };
    for (size_t i = 0; i < sizeof(stats) / sizeof(stats[0]); i++) {
        double ms = times[stats[i].index] * 1e3;
        printf("summary,%s,%s,%zu,%zu,%zu,%.6f,%.6f,%.3e\n",
               variant, stats[i].name, n, n, n, ms, flop / times[stats[i].index] / 1e9,
               max_diff);
    }
}

int main(void) {
    static const variant_t variants[] = {
        {"naive_scalar", dgemm_naive, 0, 0, 0, 0},
        {"blocked_autovec", dgemm_blocked, 0, 0, 0, 0},
        {"rvv_mr2_m8_p1", dgemm_rvv, 2, 8, 64, 1},
        {"rvv_mr8_m2_p1", dgemm_rvv, 8, 2, 128, 1},
    };
    static const struct { size_t n; int reps; } cases[] = {
        {160, 15}, {256, 13}, {512, 9}, {1024, 5},
    };
    printf("section,variant,stat_or_rep,n,m,k,ms,gflops,max_diff\n");
    for (size_t ci = 0; ci < sizeof(cases) / sizeof(cases[0]); ci++) {
        size_t n = cases[ci].n, elems = n * n;
        int reps = cases[ci].reps;
        double *a = alloc_mat(elems), *b = alloc_mat(elems);
        double *ref = alloc_mat(elems), *c = alloc_mat(elems);
        if (!a || !b || !ref || !c) return 2;
        mat_fill(a, elems, 1234 + (unsigned)n);
        mat_fill(b, elems, 5678 + (unsigned)n);
        for (size_t i = 0; i < elems; i++) ref[i] = c[i] = 0.0;
        dgemm_naive(n, n, n, a, n, b, n, ref, n);

        for (size_t vi = 0; vi < sizeof(variants) / sizeof(variants[0]); vi++) {
            const variant_t *v = &variants[vi];
            double *times = malloc((size_t)reps * sizeof(times[0]));
            if (!times) return 2;
            if (v->mr) dgemm_rvv_config(v->mr, v->lmul, v->kc, v->pipe);
            for (size_t i = 0; i < elems; i++) c[i] = 0.0;
            v->fn(n, n, n, a, n, b, n, c, n); // warm-up and correctness output
            double max_diff = max_abs_diff(c, ref, elems);
            for (int rep = 0; rep < reps; rep++) {
                for (size_t i = 0; i < elems; i++) c[i] = 0.0;
                double t0 = now_sec();
                v->fn(n, n, n, a, n, b, n, c, n);
                double elapsed = now_sec() - t0;
                times[rep] = elapsed;
                printf("raw,%s,%d,%zu,%zu,%zu,%.6f,%.6f,%.3e\n", v->name, rep + 1,
                       n, n, n, elapsed * 1e3, 2.0 * n * n * n / elapsed / 1e9,
                       max_diff);
            }
            print_summary(v->name, n, times, reps, max_diff);
            free(times);
        }
        free(a); free(b); free(ref); free(c);
    }
    return 0;
}
