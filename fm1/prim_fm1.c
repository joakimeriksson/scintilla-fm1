/* SPDX-License-Identifier: GPL-3.0-only */
/* fm1/prim.h on the FM-1: RES[0] "PRIM", RES[1] count, RES[2 + k] hashes, RES[64 + 8k + i] values */
#include "prim.h"
#define RES ((volatile uint32_t *)0x01C80000u)
void *memset(void *d, int c, unsigned n) { unsigned char *p = d; while (n--) *p++ = (unsigned char)c; return d; }
void *memcpy(void *d, const void *s, unsigned n) { unsigned char *p = d; const unsigned char *q = s; while (n--) *p++ = *q++; return d; }
static uint32_t hash[64], vals[64][8];
int main(void)
{
    extern uint32_t __data_start[], __data_end[], __data_load[], __bss_start[], __bss_end[];
    uint32_t i;
    for (i = 0; &__data_start[i] < __data_end; i++) __data_start[i] = __data_load[i];
    for (i = 0; &__bss_start[i] < __bss_end; i++) __bss_start[i] = 0;
    prim_run(hash, vals);
    for (int k = 0; k < N_PRIMS; k++) {
        RES[2 + k] = hash[k];
        for (int j = 0; j < 8; j++) RES[64 + 8 * k + j] = vals[k][j];
    }
    RES[1] = N_PRIMS;
    RES[0] = 0x4D495250u;        /* "PRIM" */
    for (;;) {}
    return 0;
}
