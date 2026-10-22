/* SPDX-License-Identifier: GPL-3.0-only */
/* Render a scenario (tools/scenario.mjs) through the C engine on this computer.
 *
 *   sc_render voice PRESET SCENARIO OUT.f32   one sc_voice, every note into it: what
 *                                             tools/ref_render.mjs does with VoiceCore (mono float32)
 *   sc_render synth PRESET SCENARIO OUT.wav   the whole instrument (16-bit stereo WAV)
 *   sc_render list                            the presets, by index
 *   sc_render reverb ALGO SIZE DAMP SEC OUT.f32   the reverb's impulse response alone, wet only
 *                                             (stereo float32; ALGO 0..3, SIZE DAMP 0..1)
 *
 * The host may use floats and stdio; the engine (engine/) may not. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "../engine/sc_synth.h"
#include "../engine/sc_fixed.h"
#include "../engine/sc_presets.h"

typedef struct { double t; int on, note; double vel; } ev_t;
typedef struct { double dur; ev_t ev[1024]; int n; int has_joy, has_perf; double joy[2], perf[4]; } scen_t;

static void parse(const char *path, scen_t *sc)
{
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); exit(1); }
    char line[256];
    memset(sc, 0, sizeof *sc);
    sc->dur = 2;
    while (fgets(line, sizeof line, f)) {
        char *h = strchr(line, '#');
        if (h) *h = 0;
        char w[16];
        double a = 0, b = 0, c = 1, d = 0;
        int k = sscanf(line, "%15s %lf %lf %lf %lf", w, &a, &b, &c, &d);
        if (k < 1) continue;
        if (!strcmp(w, "dur")) sc->dur = a;
        else if (!strcmp(w, "on")) sc->ev[sc->n++] = (ev_t){ a, 1, (int)b, k >= 4 ? c : 1 };
        else if (!strcmp(w, "off")) sc->ev[sc->n++] = (ev_t){ a, 0, (int)b, 0 };
        else if (!strcmp(w, "joy")) { sc->has_joy = 1; sc->joy[0] = a; sc->joy[1] = b; }
        else if (!strcmp(w, "perf")) { sc->has_perf = 1; sc->perf[0] = a; sc->perf[1] = b; sc->perf[2] = c; sc->perf[3] = d; }
        else { fprintf(stderr, "scenario: unknown line %s\n", line); exit(1); }
    }
    fclose(f);
    /* stable sort by time, as render.ts sorts */
    for (int i = 1; i < sc->n; i++)
        for (int j = i; j > 0 && sc->ev[j - 1].t > sc->ev[j].t; j--) { ev_t t = sc->ev[j]; sc->ev[j] = sc->ev[j - 1]; sc->ev[j - 1] = t; }
}

static int32_t q16(double v) { return (int32_t)lround(v * 65536.0); }

static void perf_of(const scen_t *sc, sc_perf_t *p)
{
    sc_perf_default(p);
    if (sc->has_joy) { p->joy_x = q16(sc->joy[0]); p->joy_y = q16(sc->joy[1]); }
    if (sc->has_perf) { p->bend_osc = q16(sc->perf[0]); p->bend_filt = q16(sc->perf[1]); p->lfo2_osc = q16(sc->perf[2]); p->lfo2_filt = q16(sc->perf[3]); }
}

/* render.ts's loop: events land on the first sample at or after their time, runs end at the next */
static void run_voice(const sc_patch_t *P, const scen_t *sc, const char *out)
{
    long n = (long)floor(sc->dur * SC_FS);
    int32_t *buf = calloc((size_t)n, sizeof *buf);
    float *f = malloc((size_t)n * sizeof *f);
    sc_perf_t perf;
    sc_prep_t prep;
    sc_voice_t v;
    perf_of(sc, &perf);
    sc_prep(&prep, &P->layer[0], &perf);
    sc_voice_init(&v, 12345);
    int e = 0;
    long i = 0;
    while (i < n) {
        double t = (double)i / SC_FS;
        while (e < sc->n && sc->ev[e].t <= t) {
            if (sc->ev[e].on) sc_voice_note_on(&v, &prep, sc->ev[e].note, q16(sc->ev[e].vel));
            else sc_voice_note_off(&v, &prep);
            e++;
        }
        long next = n;
        if (e < sc->n) {
            long c = (long)ceil(sc->ev[e].t * SC_FS);
            next = c < i + 1 ? i + 1 : c > n ? n : c;
        }
        /* runs of at most 128, as tools/ref_render.mjs (the AudioWorklet's quantum): a voice checks
         * for silence only at the start of a run, so the run length is part of what it plays */
        while (i < next) {
            long m = next - i > 128 ? 128 : next - i;
            sc_voice_render(&v, &prep, buf + i, (uint32_t)m);
            i += m;
        }
    }
    for (long k = 0; k < n; k++) f[k] = (float)buf[k] / (1 << 20);
    FILE *o = fopen(out, "wb");
    fwrite(f, sizeof *f, (size_t)n, o);
    fclose(o);
}

static void wav_header(FILE *o, long frames)
{
    uint32_t data = (uint32_t)frames * 4, v;
    uint16_t h;
    fwrite("RIFF", 1, 4, o); v = 36 + data; fwrite(&v, 4, 1, o); fwrite("WAVEfmt ", 1, 8, o);
    v = 16; fwrite(&v, 4, 1, o); h = 1; fwrite(&h, 2, 1, o); h = 2; fwrite(&h, 2, 1, o);
    v = SC_FS; fwrite(&v, 4, 1, o); v = SC_FS * 4; fwrite(&v, 4, 1, o); h = 4; fwrite(&h, 2, 1, o);
    h = 16; fwrite(&h, 2, 1, o); fwrite("data", 1, 4, o); fwrite(&data, 4, 1, o);
}

/* the instrument in 256-frame blocks, as the FM-1 calls it; events at block starts */
static void run_synth(const sc_patch_t *P, const scen_t *sc, const char *out)
{
    static sc_synth_t s;
    long n = (long)floor(sc->dur * SC_FS);
    sc_init(&s, P);
    perf_of(sc, &s.perf);
    sc_reprep(&s);
    FILE *o = fopen(out, "wb");
    wav_header(o, n);
    int e = 0;
    int32_t blk[512];
    int16_t pcm[512];
    for (long i = 0; i < n; i += 256) {
        uint32_t m = (uint32_t)(n - i < 256 ? n - i : 256);
        while (e < sc->n && sc->ev[e].t * SC_FS < i + m) {
            if (sc->ev[e].on) sc_post(&s, SC_EV_NOTE_ON, (uint8_t)sc->ev[e].note, q16(sc->ev[e].vel));
            else sc_post(&s, SC_EV_NOTE_OFF, (uint8_t)sc->ev[e].note, 0);
            e++;
        }
        memset(blk, 0, sizeof blk);
        sc_render(&s, blk, m);
        for (uint32_t k = 0; k < 2 * m; k++) pcm[k] = (int16_t)blk[k];
        fwrite(pcm, 2, 2 * m, o);
    }
    fclose(o);
}

int main(int argc, char **argv)
{
    if (argc >= 2 && !strcmp(argv[1], "list")) {
        for (int i = 0; i < SC_N_PRESETS; i++)
            printf("%2d  %s %2d  %s\n", i, SC_PRESET_ADDR[i] >= 100 ? "MEM" : "PRE", SC_PRESET_ADDR[i] % 100, SC_PRESETS[i].name);
        return 0;
    }
    if (argc == 7 && !strcmp(argv[1], "reverb")) {
        static sc_reverb_t r;
        sc_reverb_p_t rp = { 1, (int8_t)atoi(argv[2]), q16(atof(argv[3])), q16(atof(argv[4])), SC_ONE16 };
        sc_reverb_prep(&r, &rp);
        r.dry = 0;
        uint32_t frames = (uint32_t)(atof(argv[5]) * SC_FS);
        float *out = malloc((size_t)frames * 2 * sizeof *out);
        int32_t L[256], R[256];
        for (uint32_t i = 0; i < frames; i += 256) {
            uint32_t m = frames - i < 256 ? frames - i : 256;
            memset(L, 0, sizeof L); memset(R, 0, sizeof R);
            if (i == 0) L[0] = R[0] = SC_ONE20;                         /* a unit impulse, both sides */
            sc_reverb_run(&r, L, R, m);
            for (uint32_t k = 0; k < m; k++) { out[2 * (i + k)] = (float)L[k] / SC_ONE20; out[2 * (i + k) + 1] = (float)R[k] / SC_ONE20; }
        }
        FILE *f = fopen(argv[6], "wb");
        if (!f) { perror(argv[6]); return 1; }
        fwrite(out, sizeof *out, (size_t)frames * 2, f);
        fclose(f);
        return 0;
    }
    if (argc != 5) { fprintf(stderr, "usage: sc_render voice|synth PRESET SCENARIO OUT | reverb ... | list\n"); return 2; }
    int p = atoi(argv[2]);
    if (p < 0 || p >= SC_N_PRESETS) { fprintf(stderr, "no preset %d\n", p); return 2; }
    scen_t *sc = malloc(sizeof *sc);
    parse(argv[3], sc);
    if (!strcmp(argv[1], "voice")) run_voice(&SC_PRESETS[p], sc, argv[4]);
    else run_synth(&SC_PRESETS[p], sc, argv[4]);
    return 0;
}
