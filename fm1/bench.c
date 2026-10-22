/* SPDX-License-Identifier: GPL-3.0-only */
/* The engine as a bare-metal pi32v2 program for fm1-emu (after fm1-emu/fm1-sid/fm1/bench.c): no
 * RTOS, no HAL, just the CPU. bench_mark() brackets each config's timed blocks (break on it with
 * --break-pc; the step counts are instructions). Results land in RAM for --dump:
 *   RES[0] "SXFB", RES[1] configs, RES[2 + i] config i's hash,
 *   RES[64..] the first block of config 0 (512 words), to find where a mismatch starts */
#include <stdint.h>
#include "workload.h"

#define RES ((volatile uint32_t *)0x01C80000u)

void *memset(void *d, int c, unsigned n) { unsigned char *p = d; while (n--) *p++ = (unsigned char)c; return d; }
void *memcpy(void *d, const void *s, unsigned n) { unsigned char *p = d; const unsigned char *q = s; while (n--) *p++ = *q++; return d; }

static int32_t out[512];

__attribute__((noinline)) void bench_mark(uint32_t what) { RES[63] = what; }

int main(void)
{
    extern uint32_t __data_start[], __data_end[], __data_load[], __bss_start[], __bss_end[];
    uint32_t i;
    for (i = 0; &__data_start[i] < __data_end; i++)
        __data_start[i] = __data_load[i];
    for (i = 0; &__bss_start[i] < __bss_end; i++)
        __bss_start[i] = 0;
    for (int c = 0; c < WL_N; c++) {
        uint32_t h = 2166136261u;
        wl_start(&WL[c]);
        for (int b = 0; b < WL_WARM; b++) {
            wl_block(out);
            h = wl_hash(h, out);
            if (c == 0 && b == 0)
                for (i = 0; i < 512; i++) RES[64 + i] = (uint32_t)out[i];
        }
        bench_mark(2 * c);
        for (int b = 0; b < WL_BLOCKS; b++) { wl_block(out); h = wl_hash(h, out); }
        bench_mark(2 * c + 1);
        RES[2 + c] = h;
    }
    RES[1] = WL_N;
    RES[0] = 0x42465853u;        /* "SXFB" */
    bench_mark(0xFFFFu);
    /* done: jump outside every code region, which halts fm1-emu at once (else it spins to --steps) */
    void (*volatile stop)(void) = 0;
    stop();
    for (;;) {}
    return 0;
}
