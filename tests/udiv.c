/* SPDX-License-Identifier: GPL-3.0-only */
/* sc_udiv64 (two 32-bit divides) against sc_udiv64_bits (the bit loop), bit for bit: random
 * operands of every size, the powers of two the engine divides, and the edges (d = 0, d = 1, a
 * quotient of all ones, a quotient that does not fit). tests/run.sh runs it. */
#include <stdint.h>
#include <stdio.h>
#include "../engine/sc_fixed.h"

static uint64_t x = 88172645463325252ull;
static uint64_t rnd(void) { x ^= x << 13; x ^= x >> 7; x ^= x << 17; return x; }

int main(void)
{
    long bad = 0, n = 0;
#define CHECK(nn, dd) do { uint64_t n_ = (nn); uint32_t d_ = (dd); n++; \
        if (sc_udiv64(n_, d_) != sc_udiv64_bits(n_, d_) && bad++ < 5) \
            printf("udiv: %llx / %x: %x, the bit loop %x\n", (unsigned long long)n_, d_, sc_udiv64(n_, d_), sc_udiv64_bits(n_, d_)); } while (0)
    for (long i = 0; i < 20000000; i++) {
        uint64_t nn = rnd() >> (rnd() % 64);
        uint32_t dd = (uint32_t)(rnd() >> (32 + rnd() % 32));
        if (i % 3 == 0) nn = (uint64_t)1 << (30 + rnd() % 30);
        CHECK(nn, dd);
    }
    for (uint32_t s = 0; s < 32; s++)
        for (uint32_t k = 0; k < 64; k++) {
            uint32_t dd = (1u << s) + k - 32;
            CHECK((uint64_t)1 << 54, dd); CHECK((uint64_t)1 << 38, dd); CHECK(((uint64_t)dd << 32) - 1, dd);
            CHECK((uint64_t)dd << 32, dd); CHECK(~0ull, dd); CHECK(0, dd);
        }
    printf("udiv: %ld divisions, %ld differ\n", n, bad);
    return bad != 0;
}
