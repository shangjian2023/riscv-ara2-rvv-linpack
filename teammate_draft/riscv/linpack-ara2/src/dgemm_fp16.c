// dgemm_fp16.c - low-precision DGEMM study (Ozaki-lite).
//
// Two kernels built on RVV widening multiply-accumulate (fp16 inputs, fp32
// accumulator, vfwmacc):
//   f16 direct : C(f32) = A(f16) * B(f16)          -- 1 pass, fp16 accuracy
//   f16 split2 : a = a_hi + a_lo (each fp16), same for b; keep three products
//                a_hi*b_hi + a_hi*b_lo + a_lo*b_hi -- 3 passes, ~fp32 accuracy
// On Ara2 the FP16 datapath is 4x SIMD vs FP64 (fpnew 64-bit lanes), so the
// 3-pass split still yields ~4/3x the FP64 throughput at near-FP32 accuracy.
//
// Kernel shape mirrors the FP64 engine (MR x VL register blocking, packed A,
// unit-stride B) but with SEW=16 loads and f32 accumulators of double LMUL.
#include <riscv_vector.h>
#include <math.h>
#include "common.h"
#include "dgemm.h"

#define FP16_MR 8

// split one fp64 array into hi/lo fp16 halves (O(n), amortized)
static void split_f16(const double *src, size_t n, _Float16 *hi, _Float16 *lo) {
    for (size_t i = 0; i < n; i++) {
        _Float16 h = (_Float16)src[i];
        hi[i] = h;
        lo[i] = (_Float16)(src[i] - (double)h);
    }
}

// C(f64 out, computed in f32) += A(f16) * B(f16), row-major, C pre-zeroed
static void gemm_f16_core(size_t n, size_t m, size_t k, const _Float16 *a,
                          size_t lda, const _Float16 *b, size_t ldb,
                          float *c, size_t ldc) {
    const size_t vlmax = __riscv_vsetvlmax_e32m2(); // acc groups m2
    for (size_t j0 = 0; j0 < m; j0 += vlmax) {
        const size_t vl = __riscv_vsetvl_e32m2(m - j0);
        for (size_t i0 = 0; i0 + FP16_MR <= n; i0 += FP16_MR) {
            vfloat32m2_t c0, c1, c2, c3, c4, c5, c6, c7;
            // load C accumulators (f32)
            c0 = __riscv_vle32_v_f32m2(&c[(i0 + 0) * ldc + j0], vl);
            c1 = __riscv_vle32_v_f32m2(&c[(i0 + 1) * ldc + j0], vl);
            c2 = __riscv_vle32_v_f32m2(&c[(i0 + 2) * ldc + j0], vl);
            c3 = __riscv_vle32_v_f32m2(&c[(i0 + 3) * ldc + j0], vl);
            c4 = __riscv_vle32_v_f32m2(&c[(i0 + 4) * ldc + j0], vl);
            c5 = __riscv_vle32_v_f32m2(&c[(i0 + 5) * ldc + j0], vl);
            c6 = __riscv_vle32_v_f32m2(&c[(i0 + 6) * ldc + j0], vl);
            c7 = __riscv_vle32_v_f32m2(&c[(i0 + 7) * ldc + j0], vl);
            for (size_t kk = 0; kk < k; kk++) {
                vfloat16m1_t vb = __riscv_vle16_v_f16m1((const _Float16 *)(b + kk * ldb + j0), vl);
                c0 = __riscv_vfwmacc_vf_f32m2(c0, a[(i0 + 0) * lda + kk], vb, vl);
                c1 = __riscv_vfwmacc_vf_f32m2(c1, a[(i0 + 1) * lda + kk], vb, vl);
                c2 = __riscv_vfwmacc_vf_f32m2(c2, a[(i0 + 2) * lda + kk], vb, vl);
                c3 = __riscv_vfwmacc_vf_f32m2(c3, a[(i0 + 3) * lda + kk], vb, vl);
                c4 = __riscv_vfwmacc_vf_f32m2(c4, a[(i0 + 4) * lda + kk], vb, vl);
                c5 = __riscv_vfwmacc_vf_f32m2(c5, a[(i0 + 5) * lda + kk], vb, vl);
                c6 = __riscv_vfwmacc_vf_f32m2(c6, a[(i0 + 6) * lda + kk], vb, vl);
                c7 = __riscv_vfwmacc_vf_f32m2(c7, a[(i0 + 7) * lda + kk], vb, vl);
            }
            __riscv_vse32_v_f32m2(&c[(i0 + 0) * ldc + j0], c0, vl);
            __riscv_vse32_v_f32m2(&c[(i0 + 1) * ldc + j0], c1, vl);
            __riscv_vse32_v_f32m2(&c[(i0 + 2) * ldc + j0], c2, vl);
            __riscv_vse32_v_f32m2(&c[(i0 + 3) * ldc + j0], c3, vl);
            __riscv_vse32_v_f32m2(&c[(i0 + 4) * ldc + j0], c4, vl);
            __riscv_vse32_v_f32m2(&c[(i0 + 5) * ldc + j0], c5, vl);
            __riscv_vse32_v_f32m2(&c[(i0 + 6) * ldc + j0], c6, vl);
            __riscv_vse32_v_f32m2(&c[(i0 + 7) * ldc + j0], c7, vl);
        }
        // i-tail rows
        for (size_t i0 = n - (n % FP16_MR); i0 < n; i0++) {
            vfloat32m2_t c0 = __riscv_vle32_v_f32m2(&c[i0 * ldc + j0], vl);
            for (size_t kk = 0; kk < k; kk++) {
                vfloat16m1_t vb = __riscv_vle16_v_f16m1((const _Float16 *)(b + kk * ldb + j0), vl);
                c0 = __riscv_vfwmacc_vf_f32m2(c0, a[i0 * lda + kk], vb, vl);
            }
            __riscv_vse32_v_f32m2(&c[i0 * ldc + j0], c0, vl);
        }
    }
}

// public: direct fp16 gemm; c_ref must already hold the fp64 reference result.
// returns max relative deviation of the fp16 computation from the reference.
void dgemm_f16_direct(size_t n, size_t m, size_t k, const double *a,
                      const double *b, const double *c_ref, double *rel_err_out) {
    _Float16 *ah = malloc(n * k * 2), *bh = malloc(k * m * 2);
    float *cf = calloc(n * m, sizeof(float));
    for (size_t i = 0; i < n * k; i++) ah[i] = (_Float16)a[i];
    for (size_t i = 0; i < k * m; i++) bh[i] = (_Float16)b[i];
    gemm_f16_core(n, m, k, ah, k, bh, m, cf, m);
    double max_rel = 0.0;
    for (size_t i = 0; i < n * m; i++) {
        double e = fabs((double)cf[i] - c_ref[i]) / (fabs(c_ref[i]) + 1e-30);
        if (e > max_rel) max_rel = e;
    }
    *rel_err_out = max_rel;
    free(ah); free(bh); free(cf);
}

// public: 3-pass split-fp16 gemm (Ozaki-lite), near-fp32 accuracy
void dgemm_f16_split2(size_t n, size_t m, size_t k, const double *a,
                      const double *b, const double *c_ref, double *rel_err_out) {
    _Float16 *ah = malloc(n * k * 2), *al = malloc(n * k * 2);
    _Float16 *bh = malloc(k * m * 2), *bl = malloc(k * m * 2);
    float *cf = calloc(n * m, sizeof(float));
    split_f16(a, n * k, ah, al);
    split_f16(b, k * m, bh, bl);
    gemm_f16_core(n, m, k, ah, k, bh, m, cf, m);  // hi*hi
    gemm_f16_core(n, m, k, ah, k, bl, m, cf, m);  // hi*lo
    gemm_f16_core(n, m, k, al, k, bh, m, cf, m);  // lo*hi
    double max_rel = 0.0;
    for (size_t i = 0; i < n * m; i++) {
        double e = fabs((double)cf[i] - c_ref[i]) / (fabs(c_ref[i]) + 1e-30);
        if (e > max_rel) max_rel = e;
    }
    *rel_err_out = max_rel;
    free(ah); free(al); free(bh); free(bl); free(cf);
}
