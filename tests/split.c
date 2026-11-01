/* SPDX-License-Identifier: GPL-3.0-only */
/* sc_render split between two threads (sc_render_split / sc_render_voices on lanes 0 and 1 at the same
 * time / sc_render_end), as fm1-dock's module splits it between the FM-1's cores, against sc_render:
 * the same samples. Every preset, and every fourth as a double (both layers), with an 8-note chord
 * struck, repeated and released, in runs of 256, 192 and 128 frames. Built with -DSC_LANES=2 -pthread
 * (tests/run.sh). */
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include "../engine/sc_synth.h"
#include "../engine/sc_presets.h"

static sc_synth_t A, B;
static int32_t bus1[2][256];
static uint32_t job_mask, job_n;
static atomic_int go, done, quit;

static void *core1(void *arg)
{
    (void)arg;
    for (int seen = 0;;) {
        while (atomic_load(&go) == seen && !atomic_load(&quit)) {}
        if (atomic_load(&quit)) return 0;
        seen++;
        sc_render_voices(&B, bus1, job_mask, 1, job_n);
        atomic_fetch_add(&done, 1);
    }
}

int main(void)
{
    static const uint8_t chord[8] = { 36, 43, 48, 52, 55, 59, 62, 67 };
    pthread_t t;
    pthread_create(&t, 0, core1, 0);
    long bad = 0, blocks = 0;
    for (int c = 0; c < SC_N_PRESETS + SC_N_PRESETS / 4; c++) {
        sc_patch_t P = SC_PRESETS[c < SC_N_PRESETS ? c : 4 * (c - SC_N_PRESETS)];
        if (c >= SC_N_PRESETS) { P.voice_mode = SC_VM_DOUBLE; P.layer[1] = P.layer[0]; P.layer[1].o2_detune += 7; }
        sc_init(&A, &P);
        sc_init(&B, &P);
        for (int b = 0; b < 160; b++) {
            int32_t oa[512], ob[512];
            uint32_t n = 256 - (b % 3) * 64;
            for (int k = 0; k < 8; k++) {
                int32_t vel = 30000 + 4000 * k;
                if (b % 40 == 0) { sc_post(&A, SC_EV_NOTE_ON, chord[k], vel); sc_post(&B, SC_EV_NOTE_ON, chord[k], vel); }
                if (b % 40 == 25) { sc_post(&A, SC_EV_NOTE_OFF, chord[k], 0); sc_post(&B, SC_EV_NOTE_OFF, chord[k], 0); }
            }
            memset(oa, 0, sizeof oa);
            memset(ob, 0, sizeof ob);
            sc_render(&A, oa, n);
            sc_render_begin(&B);
            uint32_t m1, m0 = sc_render_split(&B, &m1);
            job_mask = m1;
            job_n = n;
            int d = atomic_load(&done);
            atomic_fetch_add(&go, 1);                  /* core 1: the other half */
            sc_render_voices(&B, B.bus, m0, 0, n);
            while (atomic_load(&done) == d) {}
            sc_render_end(&B, (const int32_t (*)[256])bus1, ob, n);
            blocks++;
            if (memcmp(oa, ob, 2 * n * sizeof oa[0]) && bad++ < 5)
                printf("split: config %d block %d differs\n", c, b);
        }
    }
    atomic_store(&quit, 1);
    pthread_join(t, 0);
    printf("split: %ld blocks on two threads, %ld differ from sc_render\n", blocks, bad);
    return bad != 0;
}
