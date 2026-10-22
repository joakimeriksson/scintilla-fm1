/* SPDX-License-Identifier: GPL-3.0-only */
/* The engine alone, as the firmware drives it, for tests/emu_test.py to compare the FM-1's sound with:
 *   engine_ref K N [NOTE [PRESET]]   K silent blocks (the time the synth ran before the note: its chorus
 *                                    runs freely), then NOTE at velocity 100 for N blocks; raw 16-bit
 *                                    stereo to stdout, before the MASTER knob */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sx_synth.h"
#include "sx_presets.h"
static sx_synth_t s;
int main(int argc, char **argv)
{
    int K = atoi(argv[1]), N = atoi(argv[2]), note = argc > 3 ? atoi(argv[3]) : 60, preset = argc > 4 ? atoi(argv[4]) : 0;
    int32_t blk[512]; int16_t pcm[512];
    sx_init(&s, &SX_PRESETS[preset]);
    sx_perf_default(&s.perf);
    sx_reprep(&s);                               /* the firmware's SX_EV_PATCH after the load */
    for (int b = 0; b < K + N; b++) {
        if (b == K) sx_post(&s, SX_EV_NOTE_ON, (uint8_t)note, 100 * 516);
        memset(blk, 0, sizeof blk);
        sx_render(&s, blk, 256);
        if (b >= K) { for (int i = 0; i < 512; i++) pcm[i] = (int16_t)blk[i]; fwrite(pcm, 2, 512, stdout); }
    }
    return 0;
}
