/* SPDX-License-Identifier: GPL-3.0-only */
/* One voice of preset 0 (note 48), its insides for the first SC_TRACE_N samples (sc_voice.c built
 * with -DSX_TRACE): on the FM-1 they land at RES, on this computer they print. Where the two first
 * differ is where the FM-1 build (or the emulator) and the host part ways. */
#include <stdint.h>
#include "../engine/sc_voice.h"
#include "../engine/sc_presets.h"
extern uint32_t sc_trace[][12];
static sc_prep_t prep;
static sc_voice_t v;
static int32_t out[400];
#ifdef HOST
#include <stdio.h>
int main(void)
{
    sc_patch_t patch;
    sc_preset_load(0, &patch);
    sc_prep(&prep, &patch.layer[0], &(sc_perf_t){ 0, 0, 19661, 19661, 32768, 32768 });
    sc_voice_init(&v, 1);
    sc_voice_note_on(&v, &prep, 48, 52000);
    sc_voice_render(&v, &prep, out, 400);
    for (int i = 0; i < 400; i++) { for (int k = 0; k < 12; k++) printf("%08x ", sc_trace[i][k]); printf("\n"); }
    return 0;
}
#else
#define RES ((volatile uint32_t *)0x01C80000u)
void *memset(void *d, int c, unsigned n) { unsigned char *p = d; while (n--) *p++ = (unsigned char)c; return d; }
void *memcpy(void *d, const void *s, unsigned n) { unsigned char *p = d; const unsigned char *q = s; while (n--) *p++ = *q++; return d; }
int main(void)
{
    extern uint32_t __data_start[], __data_end[], __data_load[], __bss_start[], __bss_end[];
    uint32_t i;
    for (i = 0; &__data_start[i] < __data_end; i++) __data_start[i] = __data_load[i];
    for (i = 0; &__bss_start[i] < __bss_end; i++) __bss_start[i] = 0;
    sc_patch_t patch;
    sc_preset_load(0, &patch);
    sc_prep(&prep, &patch.layer[0], &(sc_perf_t){ 0, 0, 19661, 19661, 32768, 32768 });
    sc_voice_init(&v, 1);
    sc_voice_note_on(&v, &prep, 48, 52000);
    sc_voice_render(&v, &prep, out, 400);
    for (i = 0; i < 400 * 12; i++) RES[16 + i] = ((uint32_t *)sc_trace)[i];
    RES[0] = 0x43415254u;        /* "TRAC" */
    for (;;) {}
    return 0;
}
#endif
