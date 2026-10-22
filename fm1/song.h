/* SPDX-License-Identifier: GPL-3.0-only */
/* A song for the emulated FM-1 to play (fm1/play.c) and this computer to check it against
 * (fm1/host_play.c): parts from build/fm1/song_ev.h (tools/song_h.py), each a scenario on one
 * preset, rendered in 256-frame blocks with events at block starts, as host/sc_render.c's synth
 * mode does. The output is 16-bit stereo, the FM-1's DAC format. */
#ifndef SONG_H
#define SONG_H
#include <stdint.h>
#include "../engine/sc_synth.h"
#include "../engine/sc_presets.h"

typedef struct { uint32_t block; uint8_t on, note; int32_t vel; } song_ev_t;
typedef struct { int preset; uint32_t frames, first, n; int32_t perf[6]; } song_part_t;
#include "../build/fm1/song_ev.h"

static sc_synth_t song_synth;

static uint32_t song_frames(void)
{
    uint32_t n = 0;
    for (int p = 0; p < SONG_N; p++) n += SONG[p].frames;
    return n;
}

/* render the whole song into pcm (song_frames() x 2 int16, interleaved) */
static void song_play(int16_t *pcm)
{
    static int32_t blk[512];
    for (int p = 0; p < SONG_N; p++) {
        const song_part_t *P = &SONG[p];
        const int32_t *q = P->perf;
        sc_init(&song_synth, &SC_PRESETS[P->preset]);
        song_synth.perf = (sc_perf_t){ q[0], q[1], q[2], q[3], q[4], q[5] };
        sc_reprep(&song_synth);
        uint32_t e = P->first, end = P->first + P->n;
        for (uint32_t i = 0, b = 0; i < P->frames; i += 256, b++) {
            uint32_t m = P->frames - i < 256 ? P->frames - i : 256;
            for (; e < end && SONG_EV[e].block == b; e++)
                sc_post(&song_synth, SONG_EV[e].on ? SC_EV_NOTE_ON : SC_EV_NOTE_OFF, SONG_EV[e].note, SONG_EV[e].vel);
            for (uint32_t k = 0; k < 512; k++) blk[k] = 0;
            sc_render(&song_synth, blk, m);
            for (uint32_t k = 0; k < 2 * m; k++) *pcm++ = (int16_t)blk[k];
        }
    }
}
#endif
