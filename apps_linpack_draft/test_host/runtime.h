// Host-side test stubs for the linpack app draft (x86, never shipped to Ara).
// runtime.h mimics the Ara interface; timing here counts nothing useful,
// only the functional path (check_phase / linpack chain) is exercised.
#pragma once
#include <stdint.h>
#include <stdio.h>

static int64_t host_t0;
static inline int64_t get_cycle_count(void) { return 0; }
static inline void start_timer(void) { host_t0 = 0; }
static inline void stop_timer(void) { host_t0 = 1; }
static inline int64_t get_timer(void) { return host_t0 ? 1000 : 0; }
