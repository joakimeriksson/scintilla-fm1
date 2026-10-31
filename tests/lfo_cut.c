/* SPDX-License-Identifier: GPL-3.0-only */
/* The per-sample path skips the samples on which the cutoff cannot have moved half a semitone
 * (cut_eval, lfo_cut_dmax): if a bound is short, it misses a coefficient update the staged render
 * makes. The presets drive the cutoff with slow triangles only, so this drives it with every LFO
 * shape at slow to fast rates, deep and shallow, with and without the delay's fade-in, the joystick's
 * depth and a filter envelope on top, and prints one hash per case. tests/run.sh builds it twice (the
 * second with -DSC_TEST_GENERAL: the per-sample path for every patch) and compares the two. */
#include <stdio.h>
#include <stdint.h>
#include "../engine/sc_synth.h"
#include "../engine/sc_presets.h"

#define Q16(x) ((int32_t)((x) * 65536.0))

int main(void)
{
    static const double rates[] = { 0.07, 1.3, 7.0, 27.7 };
    static const double depths[] = { 0.05, 0.5, 1.0 };
    static int32_t buf[128];
    for (int shape = 0; shape <= SC_LFO_SQRU; shape++)
        for (int r = 0; r < 4; r++)
            for (int d = 0; d < 3; d++)
                for (int var = 0; var < 4; var++) {
                    sc_layer_t L = SC_PRESETS[0].layer[0];          /* Chunky Synth: 2 saws, lp24 */
                    L.lfo[0] = (sc_lfo_p_t){ .shape = (int8_t)shape, .sync = 1, .rate = Q16(rates[r]),
                                             .delay = var & 1 ? Q16(0.4) : 0, .depth_a = Q16(1), .depth_b = Q16(depths[d]) };
                    L.mm[SC_MM_L1_CUT] = Q16(1);
                    L.mm[SC_MM_JX_L1] = var & 2 ? Q16(0.7) : 0;
                    if (var == 3) L.env_amt = 0;
                    sc_perf_t perf;
                    sc_perf_default(&perf);
                    perf.joy_x = Q16(0.6);
                    sc_prep_t prep;
                    sc_prep(&prep, &L, &perf);
                    sc_voice_t v;
                    sc_voice_init(&v, 99);
                    uint32_t h = 2166136261u;
                    for (int b = 0; b < 600; b++) {                   /* 1.7 s: a note, its release, another */
                        if (b == 0 || b == 400) sc_voice_note_on(&v, &prep, 48 + b / 40, Q16(0.8));
                        if (b == 250) sc_voice_note_off(&v, &prep);
                        for (int i = 0; i < 128; i++) buf[i] = 0;
                        sc_voice_render(&v, &prep, buf, 128);
                        for (int i = 0; i < 128; i++) h = (h ^ (uint32_t)buf[i]) * 16777619u;
                    }
                    printf("%d %d %d %d %08x\n", shape, r, d, var, h);
                }
    return 0;
}
