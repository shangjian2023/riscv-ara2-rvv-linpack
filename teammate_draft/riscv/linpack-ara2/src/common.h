// common.h - shared utilities: matrices, timing, verification
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <math.h>
#include <time.h>

static inline double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

// deterministic pseudo-random in [-0.5, 0.5]
static inline double frand(unsigned *seed) {
    *seed = *seed * 1664525u + 1013904223u;
    return ((double)(*seed >> 8) / 16777216.0) - 0.5;
}

static inline double *alloc_mat(size_t n) { return (double *)aligned_alloc(64, n * sizeof(double)); }

static inline void mat_fill(double *a, size_t n, unsigned seed) {
    for (size_t i = 0; i < n; i++) a[i] = frand(&seed);
}

// max abs difference between two matrices
static inline double max_abs_diff(const double *a, const double *b, size_t n) {
    double m = 0.0;
    for (size_t i = 0; i < n; i++) {
        double d = fabs(a[i] - b[i]);
        if (d > m) m = d;
    }
    return m;
}

static inline double vec_norm_inf(const double *x, size_t n) {
    double m = 0.0;
    for (size_t i = 0; i < n; i++)
        if (fabs(x[i]) > m) m = fabs(x[i]);
    return m;
}

static inline double mat_norm_inf(const double *a, size_t n) { // n x n row-major
    double m = 0.0;
    for (size_t i = 0; i < n; i++) {
        double s = 0.0;
        for (size_t j = 0; j < n; j++) s += fabs(a[i * n + j]);
        if (s > m) m = s;
    }
    return m;
}
