/* SPDX-License-Identifier: GPL-3.0-only */
/* The song (fm1/song.h) on this computer: raw 16-bit stereo PCM to stdout, for fm1/listen.py
 * to compare with what the emulated FM-1 played. */
#include <stdio.h>
#include <stdlib.h>
#include "song.h"

int main(void)
{
    uint32_t n = song_frames();
    int16_t *pcm = malloc((size_t)n * 4);
    song_play(pcm);
    fwrite(pcm, 4, n, stdout);
    return 0;
}
