/* SPDX-License-Identifier: GPL-3.0-only */
/* The song (fm1/song.h) on the emulated FM-1, bare metal like fm1/bench.c: it renders into RAM
 * at PCM and fm1/listen.py --dump's it to a WAV. RES[0] "SXPL" when done, RES[1] the frames. */
#include <stdint.h>
#include "song.h"

#define RES ((volatile uint32_t *)0x01C80000u)
/* right after RES, to the end of RAM: run with --ram 4 MiB, the most there is - RAM starts at
 * 0x01C00000, and more would cover the code at 0x02000000. 3.5 MiB is 20.8 s of stereo. */
#define PCM ((int16_t *)0x01C80010u)

void *memset(void *d, int c, unsigned n) { unsigned char *p = d; while (n--) *p++ = (unsigned char)c; return d; }
void *memcpy(void *d, const void *s, unsigned n) { unsigned char *p = d; const unsigned char *q = s; while (n--) *p++ = *q++; return d; }

int main(void)
{
    extern uint32_t __data_start[], __data_end[], __data_load[], __bss_start[], __bss_end[];
    uint32_t i;
    for (i = 0; &__data_start[i] < __data_end; i++)
        __data_start[i] = __data_load[i];
    for (i = 0; &__bss_start[i] < __bss_end; i++)
        __bss_start[i] = 0;
    song_play(PCM);
    RES[1] = song_frames();
    RES[0] = 0x4C505853u;        /* "SXPL" */
    void (*volatile stop)(void) = 0;
    stop();
    for (;;) {}
    return 0;
}
