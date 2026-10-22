/* SPDX-License-Identifier: GPL-3.0-only */
/* One held note on preset 36 "Ring mod." with fields overridden from the command line, for
 * demo/ad/fit/fit.py: one_note OUT.raw NOTE ON_S OFF_S DUR_S [field=value ...] -> 16-bit stereo.
 * Fields are sc_layer_t's (both layers) by name, plus a few patch-wide ones; values are raw Q16. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../../engine/sc_synth.h"
#include "../../../engine/sc_presets.h"

static sc_synth_t S;

static int set(sc_patch_t *p, const char *k, int32_t v)
{
#define L(name, expr) if (!strcmp(k, name)) { for (int i = 0; i < 2; i++) p->layer[i].expr = v; return 1; }
    L("o1_pwm", o1_pwm) L("o2_pwm", o2_pwm) L("o2_detune", o2_detune) L("mix_o1", mix_o1) L("mix_o2", mix_o2)
    L("cross", cross) L("cross2", cross2) L("cutoff", cutoff) L("reso", reso) L("env_amt", env_amt)
    L("key_track", key_track) L("ef_a", env_f.a) L("ef_d", env_f.d) L("ef_s", env_f.s) L("ef_r", env_f.r)
    L("ea_d", env_a.d) L("ea_s", env_a.s) L("ea_r", env_a.r) L("lfo1_rate", lfo[0].rate)
    L("lfo1_delay", lfo[0].delay) L("lfo1_da", lfo[0].depth_a) L("glide_time", glide_time)
    L("glide_amt", glide_amt) L("mm4", mm[4]) L("mm12", mm[12]) L("flt_mode", flt_mode) L("ring", ring)
#undef L
    if (!strcmp(k, "volume")) { p->volume = v; return 1; }
    if (!strcmp(k, "rev_on")) { p->fx.reverb.on = (int8_t)v; return 1; }
    if (!strcmp(k, "rev_mix")) { p->fx.reverb.mix = v; return 1; }
    if (!strcmp(k, "cho_mix")) { p->fx.chorus.mix = v; return 1; }
    if (!strcmp(k, "cho_depth")) { p->fx.chorus.depth = v; return 1; }
    if (!strcmp(k, "cho_rate")) { p->fx.chorus.rate = v; return 1; }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 6) { fprintf(stderr, "usage: one_note OUT.raw NOTE ON_S OFF_S DUR_S [field=value ...]\n"); return 2; }
    static sc_patch_t p;
    p = SC_PRESETS[36];
    for (int i = 6; i < argc; i++) {
        char *e = strchr(argv[i], '=');
        if (!e) return 2;
        *e = 0;
        if (!set(&p, argv[i], (int32_t)strtol(e + 1, 0, 10))) { fprintf(stderr, "no field %s\n", argv[i]); return 2; }
    }
    int note = atoi(argv[2]);
    uint32_t on = (uint32_t)(atof(argv[3]) * 44100) / 256, off = (uint32_t)(atof(argv[4]) * 44100) / 256;
    uint32_t frames = (uint32_t)(atof(argv[5]) * 44100);
    sc_init(&S, &p);
    int16_t *pcm = malloc((size_t)frames * 4), *q = pcm;
    static int32_t blk[512];
    for (uint32_t i = 0, b = 0; i < frames; i += 256, b++) {
        uint32_t m = frames - i < 256 ? frames - i : 256;
        if (b == on) sc_post(&S, SC_EV_NOTE_ON, note, 65536);
        if (b == off) sc_post(&S, SC_EV_NOTE_OFF, note, 0);
        memset(blk, 0, sizeof blk);
        sc_render(&S, blk, m);
        for (uint32_t k = 0; k < 2 * m; k++) *q++ = (int16_t)blk[k];
    }
    FILE *f = fopen(argv[1], "wb");
    fwrite(pcm, 4, frames, f);
    fclose(f);
    return 0;
}
