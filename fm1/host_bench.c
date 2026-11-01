/* SPDX-License-Identifier: GPL-3.0-only */
/* fm1/bench.c's workload on this computer: the hashes the FM-1 must reproduce. */
#include <stdio.h>
#include <string.h>
#include "workload.h"

int main(int argc, char **argv)
{
    static int32_t out[512];
    if (argc > 1 && !strcmp(argv[1], "presets")) {
        for (unsigned i = 0; i < SC_N_PRESETS; i++) printf("%08x\n", wl_preset_hash(i));
        return 0;
    }
    if (argc > 1) {                             /* "block": config 0's first block, as fm1/bench.c keeps it */
        wl_start(&WL[0]);
        wl_block(out);
        for (int i = 0; i < 512; i++) printf("%08x\n", (uint32_t)out[i]);
        return 0;
    }
    for (int c = 0; c < WL_N; c++) {
        uint32_t h = 2166136261u;
        wl_start(&WL[c]);
        for (int b = 0; b < WL_WARM + WL_BLOCKS; b++) { wl_block(out); h = wl_hash(h, out); }
        printf("%08x\n", h);
    }
    return 0;
}
