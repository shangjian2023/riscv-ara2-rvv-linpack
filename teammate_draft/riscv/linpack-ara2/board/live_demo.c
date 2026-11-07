// live_demo.c - Live DGEMM benchmark with real-time screen visualization
// on CanMV-K230 (C908, RVV 1.0). Runs actual GEMM, draws progress bars
// and performance comparison directly on the DSI display via DRM.
//
// Build: riscv64-linux-gnu-gcc -O3 -march=rv64gcv -static -o live_demo live_demo.c
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <drm/drm.h>
#include <drm/drm_mode.h>
#include <riscv_vector.h>

#ifndef DRM_MODE_CONNECTED
#define DRM_MODE_CONNECTED 1
#endif
#ifndef fourcc_code
#define fourcc_code(a,b,c,d) ((uint32_t)(a) | ((uint32_t)(b) << 8) | \
                              ((uint32_t)(c) << 16) | ((uint32_t)(d) << 24))
#endif

// ---------- Display ----------
static int drm_fd;
static unsigned char *fb;
static uint32_t fb_w, fb_h, fb_size;

// ---------- Colors (just R,G,B for fill_rect/draw_text) ----------
#define COL_BG     0x00, 0x0B, 0x1A
#define COL_TITLE  0x22, 0xD3, 0xEE
#define COL_RED    0xF8, 0x6F, 0x4E
#define COL_GREEN  0x34, 0xD3, 0x99
#define COL_GOLD   0xFB, 0xBF, 0x24
#define COL_WHITE  0xFF, 0xFF, 0xFF
#define COL_GRAY   0x94, 0xA3, 0xB8
#define COL_DARK   0x00, 0x12, 0x3A

static inline void px(int x, int y, unsigned char r, unsigned char g, unsigned char b) {
    if (x < 0 || x >= (int)fb_w || y < 0 || y >= (int)fb_h) return;
    unsigned char *p = fb + (uint64_t)y * fb_w * 4 + (uint64_t)x * 4;
    p[0] = b; p[1] = g; p[2] = r; p[3] = 0xFF;
}

static void fill_rect(int x, int y, int w, int h, unsigned char r, unsigned char g, unsigned char b) {
    for (int j = y; j < y + h; j++)
        for (int i = x; i < x + w; i++)
            px(i, j, r, g, b);
}

// 5x7 font for digits and basic chars
static const uint8_t font5x7[128][5] = {
    {0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},
    {0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},
    {0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},
    {0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},
    {0,0,0,0,0},{0x00,0x80,0x80,0x80,0x00},{0x80,0x80,0x80,0x80,0x80},{0xA0,0xA0,0xA0,0xA0,0xA0},
    {0xC0,0xC0,0xC0,0xC0,0xC0},{0,0,0,0,0},{0xE0,0xE0,0x00,0xE0,0xE0},{0x00,0x00,0x00,0x00,0x00},
    {0x60,0x90,0x90,0x90,0x60},{0x20,0x60,0x20,0x20,0x70},{0x60,0x90,0x20,0x40,0xF0},
    {0x60,0x90,0x20,0x90,0x60},{0x30,0x50,0x90,0xF0,0x10},{0xF0,0x80,0xE0,0x10,0xE0},
    {0x60,0x80,0xE0,0x90,0x60},{0xF0,0x10,0x20,0x40,0x80},{0x60,0x90,0x60,0x90,0x60},
    {0x60,0x90,0x70,0x10,0x60},{0x00,0x20,0x00,0x20,0x00},{0x00,0x20,0x00,0x20,0x20},
    {0x20,0x40,0x80,0x40,0x20},{0x00,0xE0,0x00,0xE0,0x00},{0x40,0x20,0x10,0x20,0x40},
    {0x60,0x90,0x20,0x00,0x20},{0x60,0x90,0xB0,0x80,0x60},{0x60,0x90,0xF0,0x90,0x90},
    {0xE0,0x90,0xE0,0x90,0xE0},{0x60,0x90,0x80,0x90,0x60},{0xE0,0x90,0x90,0x90,0xE0},
    {0xF0,0x80,0xE0,0x80,0xF0},{0xF0,0x80,0xE0,0x80,0x80},{0x00,0x00,0x00,0x00,0x00},
    {0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},
    // A-Z
    {0x60,0x90,0xF0,0x90,0x90},{0xE0,0x90,0xE0,0x90,0xE0},{0x60,0x90,0x80,0x90,0x60},
    {0xE0,0x90,0x90,0x90,0xE0},{0xF0,0x80,0xE0,0x80,0xF0},{0xF0,0x80,0xE0,0x80,0x80},
    {0x60,0x90,0xB0,0x90,0x70},{0x90,0x90,0xF0,0x90,0x90},{0xE0,0x40,0x40,0x40,0xE0},
    {0x70,0x10,0x10,0x90,0x60},{0x90,0xA0,0xC0,0xA0,0x90},{0x80,0x80,0x80,0x80,0xF0},
    {0x90,0xF0,0xF0,0x90,0x90},{0x90,0xD0,0xB0,0x90,0x90},{0x60,0x90,0x90,0x90,0x60},
    {0xE0,0x90,0xE0,0x80,0x80},{0x60,0x90,0x90,0xA0,0x50},{0xE0,0x90,0xE0,0xA0,0x90},
    {0x60,0x80,0x60,0x10,0xE0},{0xE0,0x40,0x40,0x40,0x40},{0x90,0x90,0x90,0x90,0x60},
    {0x90,0x90,0x90,0x60,0x60},{0x90,0x90,0xF0,0x90,0x90},{0x90,0x60,0x60,0x60,0x90},
    {0x90,0x90,0x60,0x60,0x60},{0xF0,0x10,0x20,0x40,0xF0},
    // a-z
    {0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},
    {0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},
    {0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},
    {0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},
    {0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},
    // misc
    {0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},{0,0,0,0,0},
};

static void draw_char(int x, int y, char c, int scale, unsigned char r, unsigned char g, unsigned char b) {
    if ((int)c < 32 || (int)c > 127) c = '?';
    const uint8_t *glyph = font5x7[(int)c - 32];
    for (int row = 0; row < 7; row++)
        for (int col = 0; col < 5; col++)
            if (glyph[col] & (0x40 >> row))
                fill_rect(x + col * scale, y + row * scale, scale, scale, r, g, b);
}

static void draw_text(int x, int y, const char *s, int scale, unsigned char r, unsigned char g, unsigned char b) {
    for (const char *p = s; *p; p++, x += 6 * scale)
        draw_char(x, y, *p, scale, r, g, b);
}

static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

// ---------- GEMM kernels ----------
#define N 128
static double A[N*N], B[N*N], C[N*N];

static void init_matrices(void) {
    for (int i = 0; i < N*N; i++) { A[i] = (double)(i % 17) * 0.1; B[i] = (double)(i % 23) * 0.1; C[i] = 0; }
}

// Scalar baseline (compiler won't vectorize at -O2 without -ftree-vectorize)
__attribute__((optimize("O2", "no-tree-vectorize")))
static void gemm_scalar(void) {
    for (int i = 0; i < N; i++)
        for (int l = 0; l < N; l++) {
            double a = A[i*N + l];
            for (int j = 0; j < N; j++)
                C[i*N + j] += a * B[l*N + j];
        }
}

// RVV vectorized kernel (MR=4, LMUL=8)
static void gemm_rvv(void) {
    for (int j0 = 0; j0 < N; j0 += 16) {
        int vl = N - j0 < 16 ? N - j0 : 16;
        for (int i = 0; i + 4 <= N; i += 4) {
            vfloat64m8_t c0 = __riscv_vle64_v_f64m8(&C[i*N + j0], vl);
            vfloat64m8_t c1 = __riscv_vle64_v_f64m8(&C[(i+1)*N + j0], vl);
            vfloat64m8_t c2 = __riscv_vle64_v_f64m8(&C[(i+2)*N + j0], vl);
            vfloat64m8_t c3 = __riscv_vle64_v_f64m8(&C[(i+3)*N + j0], vl);
            for (int l = 0; l < N; l++) {
                vfloat64m8_t vb = __riscv_vle64_v_f64m8(&B[l*N + j0], vl);
                c0 = __riscv_vfmacc_vf_f64m8(c0, A[i*N+l], vb, vl);
                c1 = __riscv_vfmacc_vf_f64m8(c1, A[(i+1)*N+l], vb, vl);
                c2 = __riscv_vfmacc_vf_f64m8(c2, A[(i+2)*N+l], vb, vl);
                c3 = __riscv_vfmacc_vf_f64m8(c3, A[(i+3)*N+l], vb, vl);
            }
            __riscv_vse64_v_f64m8(&C[i*N + j0], c0, vl);
            __riscv_vse64_v_f64m8(&C[(i+1)*N + j0], c1, vl);
            __riscv_vse64_v_f64m8(&C[(i+2)*N + j0], c2, vl);
            __riscv_vse64_v_f64m8(&C[(i+3)*N + j0], c3, vl);
        }
    }
}

// ---------- DRM setup (compact, reuses fbdemo logic) ----------
static int drm_setup(void) {
    drm_fd = open("/dev/dri/card0", O_RDWR);
    if (drm_fd < 0) return -1;
    struct drm_mode_card_res res;
    memset(&res, 0, sizeof(res));
    if (ioctl(drm_fd, DRM_IOCTL_MODE_GETRESOURCES, &res) < 0) return -1;
    uint32_t conn_ids[4], crtc_ids[4], enc_ids[4];
    res.connector_id_ptr = (uint64_t)(uintptr_t)conn_ids; res.count_connectors = 4;
    res.crtc_id_ptr = (uint64_t)(uintptr_t)crtc_ids; res.count_crtcs = 4;
    res.encoder_id_ptr = (uint64_t)(uintptr_t)enc_ids; res.count_encoders = 4;
    if (ioctl(drm_fd, DRM_IOCTL_MODE_GETRESOURCES, &res) < 0) return -1;

    for (int c = 0; c < res.count_connectors; c++) {
        struct drm_mode_get_connector conn;
        struct drm_mode_modeinfo modes[4];
        uint32_t encs[4], props[4], pvals[4];
        memset(&conn, 0, sizeof(conn));
        conn.connector_id = conn_ids[c];
        conn.modes_ptr = (uint64_t)(uintptr_t)modes; conn.count_modes = 4;
        conn.encoders_ptr = (uint64_t)(uintptr_t)encs; conn.count_encoders = 4;
        conn.props_ptr = (uint64_t)(uintptr_t)props; conn.prop_values_ptr = (uint64_t)(uintptr_t)pvals; conn.count_props = 4;
        if (ioctl(drm_fd, DRM_IOCTL_MODE_GETCONNECTOR, &conn) < 0) continue;
        if (conn.connection != DRM_MODE_CONNECTED || conn.count_modes == 0) continue;

        fb_w = modes[0].hdisplay; fb_h = modes[0].vdisplay;

        struct drm_mode_get_encoder enc;
        memset(&enc, 0, sizeof(enc));
        if (conn.encoder_id > 0) {
            enc.encoder_id = conn.encoder_id;
            ioctl(drm_fd, DRM_IOCTL_MODE_GETENCODER, &enc);
        } else {
            for (int e = 0; e < conn.count_encoders; e++) {
                memset(&enc, 0, sizeof(enc));
                enc.encoder_id = encs[e];
                if (ioctl(drm_fd, DRM_IOCTL_MODE_GETENCODER, &enc) == 0) break;
            }
        }
        uint32_t crtc_id = 0;
        for (int k = 0; k < res.count_crtcs; k++)
            if (enc.possible_crtcs & (1u << k)) { crtc_id = crtc_ids[k]; break; }
        if (!crtc_id) continue;

        struct drm_mode_create_dumb cre;
        memset(&cre, 0, sizeof(cre));
        cre.width = fb_w; cre.height = fb_h; cre.bpp = 32;
        if (ioctl(drm_fd, DRM_IOCTL_MODE_CREATE_DUMB, &cre) < 0) continue;

        struct drm_mode_map_dumb m;
        memset(&m, 0, sizeof(m));
        m.handle = cre.handle;
        if (ioctl(drm_fd, DRM_IOCTL_MODE_MAP_DUMB, &m) < 0) continue;

        fb = mmap(0, cre.size, PROT_READ|PROT_WRITE, MAP_SHARED, drm_fd, (off_t)(uint64_t)m.offset);
        if (fb == MAP_FAILED) continue;

        struct drm_mode_fb_cmd2 fbc2;
        memset(&fbc2, 0, sizeof(fbc2));
        fbc2.width = fb_w; fbc2.height = fb_h;
        fbc2.pixel_format = fourcc_code('A','R','2','4');
        fbc2.handles[0] = cre.handle;
        fbc2.pitches[0] = cre.pitch;
        if (ioctl(drm_fd, DRM_IOCTL_MODE_ADDFB2, &fbc2) < 0) continue;

        uint32_t conn_set[1] = {conn_ids[c]};
        struct drm_mode_crtc sc;
        memset(&sc, 0, sizeof(sc));
        sc.crtc_id = crtc_id; sc.fb_id = fbc2.fb_id;
        sc.mode_valid = 1; sc.mode = modes[0];
        sc.set_connectors_ptr = (uint64_t)(uintptr_t)conn_set;
        sc.count_connectors = 1;
        if (ioctl(drm_fd, DRM_IOCTL_MODE_SETCRTC, &sc) < 0) continue;

        fb_size = cre.size;
        fprintf(stderr, "display ON %ux%u\r\n", fb_w, fb_h);
        return 0;
    }
    return -1;
}

// ---------- Seven-segment big digits ----------
// segments: a(top), b(top-right), c(bottom-right), d(bottom), e(bottom-left), f(top-left), g(middle)
static const int seg7[10][7] = {
    {1,1,1,1,1,1,0}, // 0
    {0,1,1,0,0,0,0}, // 1
    {1,1,0,1,1,0,1}, // 2
    {1,1,1,1,0,0,1}, // 3
    {0,1,1,0,0,1,1}, // 4
    {1,0,1,1,0,1,1}, // 5
    {1,0,1,1,1,1,1}, // 6
    {1,1,1,0,0,0,0}, // 7
    {1,1,1,1,1,1,1}, // 8
    {1,1,1,1,0,1,1}, // 9
};

static void draw_seg_digit(int x, int y, int d, int w, int h, int t,
                           unsigned char r, unsigned char g, unsigned char b) {
    if (d < 0 || d > 9) return;
    int W = w - 2 * t; // inner width
    // a: top
    if (seg7[d][0]) fill_rect(x + t, y, W, t, r, g, b);
    // b: top-right
    if (seg7[d][1]) fill_rect(x + w - t, y + t, t, h / 2 - t, r, g, b);
    // c: bottom-right
    if (seg7[d][2]) fill_rect(x + w - t, y + h / 2 + t / 2, t, h / 2 - t, r, g, b);
    // d: bottom
    if (seg7[d][3]) fill_rect(x + t, y + h - t, W, t, r, g, b);
    // e: bottom-left
    if (seg7[d][4]) fill_rect(x, y + h / 2 + t / 2, t, h / 2 - t, r, g, b);
    // f: top-left
    if (seg7[d][5]) fill_rect(x, y + t, t, h / 2 - t, r, g, b);
    // g: middle
    if (seg7[d][6]) fill_rect(x + t, y + h / 2 - t / 2, W, t, r, g, b);
}

static void draw_seg_number(int x, int y, double val, int dw, int dh, int dt,
                            unsigned char r, unsigned char g, unsigned char b) {
    int int_part = (int)val;
    int dec_part = (int)((val - int_part) * 10);
    int cx = x;
    draw_seg_digit(cx, y, int_part, dw, dh, dt, r, g, b);
    cx += dw + dt;
    // decimal point
    fill_rect(cx + dt / 2, y + dh - dt * 2, dt, dt, r, g, b);
    cx += dt * 2;
    draw_seg_digit(cx, y, dec_part, dw, dh, dt, r, g, b);
    cx += dw + dt * 2;
    // 'x' as two diagonal blocks
    int xs = dw * 2 / 3;
    for (int i = 0; i < xs; i += dt) {
        fill_rect(cx + i, y + i * dh / xs, dt * 2, dt * 2, r, g, b);
        fill_rect(cx + xs - i, y + i * dh / xs, dt * 2, dt * 2, r, g, b);
    }
}

// ---------- Main demo loop ----------
int main(void) {
    if (drm_setup() < 0) {
        fprintf(stderr, "FERR display setup\r\n");
        return 1;
    }
    double flops = 2.0 * N * N * N;

    while (1) {
        // clear
        fill_rect(0, 0, fb_w, fb_h, COL_BG);
        // header bar
        fill_rect(0, 0, fb_w, 12, 0x22, 0xD3, 0xEE);
        usleep(300000);

        // --- Scalar baseline ---
        init_matrices();
        double t0 = now_sec();
        gemm_scalar();
        double t_scalar = now_sec() - t0;
        double gf_scalar = flops / t_scalar / 1e9;
        // FULL-WIDTH red bar
        fill_rect(10, 40, fb_w - 20, 60, 0xF8, 0x50, 0x30);
        fill_rect(10, 40, 8, 60, 0xFF, 0x80, 0x60);
        usleep(1500000);

        // --- RVV optimized ---
        init_matrices();
        t0 = now_sec();
        gemm_rvv();
        double t_rvv = now_sec() - t0;
        double gf_rvv = flops / t_rvv / 1e9;
        double speedup = t_scalar / t_rvv;
        // PROPORTIONAL green bar
        int gw = (int)((double)(fb_w - 20) / speedup);
        if (gw < 50) gw = 50;
        fill_rect(10, 130, gw, 60, 0x30, 0xE0, 0x70);
        fill_rect(10, 130, 8, 60, 0x60, 0xF0, 0x90);
        usleep(1500000);

        // --- Speedup: BIG seven-segment digits (gold) ---
        draw_seg_number(30, 250, speedup, 90, 180, 18, 0xFB, 0xBF, 0x24);

        // --- Bottom comparison bars (thicker) ---
        fill_rect(10, 520, fb_w - 20, 80, 0xF8, 0x50, 0x30);
        fill_rect(10, 630, gw, 80, 0x30, 0xE0, 0x70);

        // gap indicator (arrow between bars)
        int gap_x = gw + 20;
        fill_rect(gap_x, 630, fb_w - 20 - gw - 10, 80, 0x00, 0x0B, 0x1A);
        fill_rect(gap_x, 660, 20, 20, 0xFB, 0xBF, 0x24);

        fprintf(stderr, "scalar=%.3f gflops rvv=%.3f gflops speedup=%.2fx\r\n",
                gf_scalar, gf_rvv, speedup);
        usleep(8000000);
    }
    return 0;
}
