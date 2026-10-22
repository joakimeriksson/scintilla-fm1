/* SPDX-License-Identifier: GPL-3.0-only */
/* fm1/prim.h on this computer: name, hash and the first values, one line per primitive */
#include <stdio.h>
#include "prim.h"
static uint32_t hash[64], vals[64][8];
int main(void)
{
    prim_run(hash, vals);
    for (int k = 0; k < N_PRIMS; k++) {
        printf("%s|%08x|", PRIMS[k].name, hash[k]);
        for (int j = 0; j < 8; j++) printf("%08x ", vals[k][j]);
        printf("\n");
    }
    return 0;
}
