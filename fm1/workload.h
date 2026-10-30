/* SPDX-License-Identifier: GPL-3.0-only */
/* The CPU bench's workload, the same on the FM-1 (fm1/bench.c) and on this computer
 * (fm1/host_bench.c): each config plays a chord on one preset; WL_WARM blocks of 256 frames let
 * the attacks settle, then WL_BLOCKS blocks are timed. The output is hashed: the engine is all
 * integer, so the FM-1 must give the host's samples bit for bit. */
#ifndef WORKLOAD_H
#define WORKLOAD_H
#include <stdint.h>
#include "../engine/sc_synth.h"
#include "../engine/sc_presets.h"

#define WL_WARM   4
#define WL_BLOCKS 16

typedef struct { const char *what; int preset, voices, double_layer; } wl_config_t;

/* presets by index (build/sc_render list) */
static const wl_config_t WL[] = {
    { "Chunky Synth: 2 saws, lp24", 0, 1, 0 },
    { "Chunky Synth: 2 saws, lp24", 0, 4, 0 },
    { "Chunky Synth: 2 saws, lp24", 0, 8, 0 },
    { "Ring mod. (Laser Harp)",     36, 8, 0 },
    { "Sync. Harmonic Sweep",       41, 8, 0 },
    { "Brushed Cymbals: noise",     58, 8, 0 },
    { "Chunky Synth, both layers",  0, 8, 1 },
    { "Fat Sound: OSC2->OSC1 PWM",   2, 8, 0 },
    { "Metallic: + sync, glide",     3, 8, 0 },
    { "Landing",                    33, 8, 0 },
    { "Take-off: HP12 sweep",        32, 8, 0 },
};
#define WL_N ((int)(sizeof WL / sizeof WL[0]))

static sc_synth_t wl_synth;

static void wl_start(const wl_config_t *c)
{
    static const uint8_t chord[8] = { 48, 55, 60, 64, 67, 71, 74, 79 };
    sc_patch_t p = SC_PRESETS[c->preset];
    if (c->double_layer) { p.voice_mode = SC_VM_DOUBLE; p.layer[1] = p.layer[0]; }
    sc_init(&wl_synth, &p);
    for (int i = 0; i < c->voices; i++) sc_post(&wl_synth, SC_EV_NOTE_ON, chord[i], 52000);
}

static void wl_block(int32_t *out)
{
    for (int i = 0; i < 512; i++) out[i] = 0;
    sc_render(&wl_synth, out, 256);
}

static uint32_t wl_hash(uint32_t h, const int32_t *out)
{
    for (int i = 0; i < 512; i++) { h ^= (uint32_t)out[i]; h *= 16777619u; }
    return h;
}
#endif
