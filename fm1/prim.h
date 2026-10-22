/* SPDX-License-Identifier: GPL-3.0-only */
/* Each arithmetic primitive the engine leans on, over 2000 pseudo-random inputs, hashed: run on the
 * FM-1 (fm1/prim_fm1.c) and on this computer (fm1/prim_host.c), the hashes must agree. Where they
 * do not, the first differing input is recorded. Includes sx_voice.c to reach its static helpers. */
#include <stdint.h>
#include "../engine/sx_voice.c"

#define PRIM_N 2000
static uint32_t prim_seed;
static uint32_t rnd(void) { return sx_xorshift(&prim_seed); }

typedef struct { const char *name; uint32_t (*f)(void); } prim_t;

static uint32_t p_udiv64(void) { uint32_t d = rnd() | 1u; uint64_t n = ((uint64_t)(rnd() % d) << 32) | rnd(); return sx_udiv64(n, d); }
static uint32_t p_udiv64_small(void) { uint32_t d = (rnd() >> 8) | 1u; return sx_udiv64((uint64_t)1 << 54, d < (1u << 24) ? d + (1u << 24) : d); }
static uint32_t p_smul30(void) { int32_t a = (int32_t)rnd(), b = (int32_t)rnd(); return (uint32_t)(((int64_t)a * b) >> 30); }
static uint32_t p_smul16(void) { int32_t a = (int32_t)rnd() >> 4, b = (int32_t)rnd() >> 8; return (uint32_t)sx_mul(a, b, 16); }
static uint32_t p_umul_hi(void) { uint32_t a = rnd(), b = rnd(); return (uint32_t)(((uint64_t)a * b) >> 28); }
static uint32_t p_s64_sum(void) { int32_t a = (int32_t)rnd(), b = (int32_t)rnd(), c = (int32_t)rnd(), d = (int32_t)rnd();
                                  return (uint32_t)(((int64_t)a * b + (int64_t)c * d) >> 30); }
static uint32_t p_shl64(void) { uint64_t v = ((uint64_t)rnd() << 32) | rnd(); int k = (int)(rnd() & 63); return (uint32_t)((v << k) >> 32) ^ (uint32_t)(v << k); }
static uint32_t p_shr64(void) { uint64_t v = ((uint64_t)rnd() << 32) | rnd(); int k = (int)(rnd() & 63); return (uint32_t)(v >> k) ^ (uint32_t)((v >> k) >> 32); }
static uint32_t p_sar64(void) { int64_t v = (int64_t)(((uint64_t)rnd() << 32) | rnd()); int k = (int)(rnd() & 63); return (uint32_t)(v >> k) ^ (uint32_t)((uint64_t)(v >> k) >> 32); }
static uint32_t p_cmp64(void) { uint64_t a = ((uint64_t)(rnd() & 7) << 32) | rnd(), b = ((uint64_t)(rnd() & 7) << 32) | rnd(); return (a >= b) | ((a < b) << 1) | ((a == b) << 2); }
static uint32_t p_sub64(void) { uint64_t a = ((uint64_t)rnd() << 32) | rnd(), b = ((uint64_t)rnd() << 32) | rnd(); uint64_t c = a - b; return (uint32_t)c ^ (uint32_t)(c >> 32); }
static uint32_t p_pitch(void) { return sx_pitch_inc((int32_t)(rnd() % (150u << 16)) - (3 << 16)); }
static uint32_t p_cut_g(void) { return cut_g((int32_t)(rnd() % ((132u << 16) + 1))); }
static uint32_t p_exp(void) { return (uint32_t)sx_exp_neg_inv(rnd() >> 8); }
static uint32_t p_frac16(void) { uint32_t b = rnd() | 1u, a = rnd() % b; return (uint32_t)frac16(a, b); }
static uint32_t p_div32(void) { uint32_t a = rnd(), b = (rnd() >> (rnd() & 31)) | 1u; return a / b; }
static uint32_t p_sdiv32(void) { int32_t a = (int32_t)rnd(), b = (int32_t)(rnd() >> (rnd() & 30)) | 1; if (rnd() & 1) b = -b; return (uint32_t)(a / b); }
static uint32_t p_blep(void) { uint32_t dt = rnd() >> 1; return (uint32_t)blep(rnd(), dt); }
static uint32_t p_coeffs(void)
{
    static sx_voice_t v;
    static sx_prep_t p;
    p.c_base = (int32_t)(rnd() % (140u << 16)) - (4 << 16);
    p.kc_env = (int32_t)(rnd() % (120u << 16)) - (60 << 16);
    p.kc_env1 = 96 << 16; p.kc_key = 1 << 15;
    p.k_q28 = (int32_t)(rnd() % (1u << 29)) + (1 << 24);
    v.env1.level = (int32_t)(rnd() >> 2);
    v.cur = (int64_t)(rnd() % 128u) << 32;
    update_coeffs(&v, &p);
    return (uint32_t)v.a1 ^ ((uint32_t)v.a2 << 7) ^ ((uint32_t)v.a3 << 13);
}

static const prim_t PRIMS[] = {
    { "udiv64", p_udiv64 }, { "udiv64 2^54/d", p_udiv64_small }, { "s64 mul >>30", p_smul30 },
    { "sx_mul 16", p_smul16 }, { "u64 mul >>28", p_umul_hi }, { "s64 a*b+c*d", p_s64_sum },
    { "u64 <<", p_shl64 }, { "u64 >>", p_shr64 }, { "s64 >>", p_sar64 }, { "u64 compare", p_cmp64 },
    { "u64 -", p_sub64 }, { "pitch_inc", p_pitch }, { "cut_g", p_cut_g }, { "exp_neg_inv", p_exp },
    { "frac16", p_frac16 }, { "u32 /", p_div32 }, { "s32 /", p_sdiv32 }, { "blep", p_blep },
    { "update_coeffs", p_coeffs },
};
#define N_PRIMS ((int)(sizeof PRIMS / sizeof PRIMS[0]))

/* results[k]: the hash of primitive k; vals[k][i]: its first 8 values (to see the first difference) */
static void prim_run(uint32_t *hash, uint32_t vals[][8])
{
    for (int k = 0; k < N_PRIMS; k++) {
        uint32_t h = 2166136261u;
        prim_seed = 0x1234567u + (uint32_t)k;
        for (int i = 0; i < PRIM_N; i++) {
            uint32_t r = PRIMS[k].f();
            if (i < 8) vals[k][i] = r;
            h = (h ^ r) * 16777619u;
        }
        hash[k] = h;
    }
}
