// SPDX-License-Identifier: GPL-3.0-only
// Write engine/sc_presets.h from synthex-web's factory bank (packages/engine/src/presets/factory.ts),
// read as it is: every continuous value becomes Q16, every enum its index (engine/sc_patch.h).
//
//   node --experimental-transform-types tools/gen_presets.mjs [SYNTHEX_WEB_DIR]
import { writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const SYNTHEX_WEB = process.env.SYNTHEX_WEB ?? join(homedir(), 'work/ai-smarthome/audio/software-synth/synthex')
const here = dirname(fileURLToPath(import.meta.url))

const WAVE = ['triangle', 'sawtooth', 'square', 'sine', 'noise']
const FLT = ['lp24', 'lp12', 'bp12', 'bp6', 'hp12']
const LFO = ['tri', 'square', 'sample-hold', 'random', 'ramp', 'square-uni']
const GLIDE = ['off', 'glide', 'portamento']
const KEY = ['poly', 'mono', 'unison']
const VM = ['single', 'split', 'double']
const DLY = ['standard', 'tape', 'pingpong']
const REV = ['plate', 'room', 'hall', 'galactic']
const MM = ['lfo1ToOsc1Pitch', 'lfo1ToOsc2Pitch', 'lfo1ToCutoff', 'lfo1ToOsc1Pwm', 'lfo1ToOsc2Pwm', 'lfo1ToAmp',
  'lfo2ToOsc1Pitch', 'lfo2ToOsc2Pitch', 'lfo2ToCutoff', 'lfo2ToOsc1Pwm', 'lfo2ToOsc2Pwm', 'lfo2ToAmp',
  'env1ToCutoff', 'env1ToOsc2Pitch', 'joyXToLfo1Depth', 'joyXToLfo2Depth', 'joyYToCutoff', 'joyYToLfoFiltDepth',
  'velToAmp', 'velToCutoff', 'velToEnv1']

const q = (v) => {
  if (typeof v !== 'number' || !Number.isFinite(v)) throw new Error(`not a number: ${v}`)
  return Math.round(v * 65536)
}
const e = (list, v) => {
  const i = list.indexOf(v)
  if (i < 0) throw new Error(`unknown value ${v} (${list.join(', ')})`)
  return i
}
const b = (v) => (v ? 1 : 0)
const adsr = (x) => `{ ${q(x.a)}, ${q(x.d)}, ${q(x.s)}, ${q(x.r)} }`
const lfo = (x) => `{ .shape = ${e(LFO, x.shape)}, .sync = ${b(x.sync)}, .rate = ${q(x.rate)}, .delay = ${q(x.delay)}, .depth_a = ${q(x.depthA)}, .depth_b = ${q(x.depthB)} }`

export function layerC(L) {
  return `{
        .o1_wave = ${e(WAVE, L.osc1.wave)}, .o1_oct = ${L.osc1.octave}, .o1_pwm = ${q(L.osc1.pwm)},
        .o1_glide_amt = ${q(L.osc1.glide.amount)}, .o1_glide_speed = ${q(L.osc1.glide.speed)},
        .o2_wave = ${e(WAVE, L.osc2.wave)}, .o2_oct = ${L.osc2.octave}, .o2_sync = ${b(L.osc2.sync)},
        .o2_detune = ${q(L.osc2.detune)}, .o2_pwm = ${q(L.osc2.pwm)},
        .o2_glide_amt = ${q(L.osc2.glide.amount)}, .o2_glide_speed = ${q(L.osc2.glide.speed)},
        .mix_o1 = ${q(L.mix.osc1)}, .mix_o2 = ${q(L.mix.osc2)}, .mix_noise = ${q(L.mix.noise)},
        .noise_pink = ${b(L.mix.noiseColor === 'pink')}, .ring = ${b(L.mix.ringMod)},
        .cross = ${q(L.mix.crossMod)}, .cross2 = ${q(L.mix.crossMod2 ?? 0)},
        .flt_mode = ${e(FLT, L.filter.mode)}, .cutoff = ${q(L.filter.cutoff)}, .reso = ${q(L.filter.resonance)},
        .env_amt = ${q(L.filter.envAmount)}, .key_track = ${q(L.filter.keyTrack)},
        .env_f = ${adsr(L.envFilter)}, .env_a = ${adsr(L.envAmp)},
        .lfo = { ${lfo(L.lfo1)}, ${lfo(L.lfo2)} },
        .mm = { ${MM.map((k) => q(L.modMatrix[k] ?? 0)).join(', ')} },
        .glide_time = ${q(L.glide.time)}, .glide_amt = ${q(L.glide.amount)}, .glide_mode = ${e(GLIDE, L.glide.mode)},
        .glide_o1 = ${b(L.glide.osc1)}, .glide_o2 = ${b(L.glide.osc2)},
        .key_assign = ${e(KEY, L.keyAssign)}, .multi_trigger = ${b(L.multiTrigger)}, .pan = ${q(L.pan)},
    }`
}

/** ASCII for the FM-1's font, at most 27 characters */
const ascii = (s) => s.replace(/[—–]/g, '-').replace(/[^\x20-\x7e]/g, '?').slice(0, 27)

export function patchC(P) {
  const fx = P.fx
  return `{
    .name = ${JSON.stringify(ascii(P.name))},
    .layer = { ${layerC(P.upper)}, ${layerC(P.lower)} },
    .voice_mode = ${e(VM, P.voiceMode)}, .split = ${P.splitPoint},
    .fx = {
        .chorus = { .on = ${b(fx.chorus.enabled)}, .mode = ${fx.chorus.mode}, .mix = ${q(fx.chorus.mix)}, .rate = ${q(fx.chorus.rate)}, .depth = ${q(fx.chorus.depth)} },
        .delay = { .on = ${b(fx.delay.enabled)}, .mode = ${e(DLY, fx.delay.mode)}, .time = ${q(fx.delay.time)}, .feedback = ${q(fx.delay.feedback)}, .tone = ${q(fx.delay.tone)}, .spread = ${q(fx.delay.spread)}, .mix = ${q(fx.delay.mix)} },
        .reverb = { .on = ${b(fx.reverb.enabled)}, .algo = ${e(REV, fx.reverb.algorithm)}, .size = ${q(fx.reverb.size)}, .damping = ${q(fx.reverb.damping)}, .mix = ${q(fx.reverb.mix)} },
    },
    .tune = ${q(P.master.tune)}, .fine_tune = ${q(P.master.fineTune)}, .volume = ${q(P.master.volume)},
    .unison_detune = ${q(P.master.unisonDetune)}, .polyphony = ${P.master.polyphony}, .limiter = ${b(P.master.limiter)},
}`
}

export async function factory() {
  const f = (await import(join(SYNTHEX_WEB, 'packages/engine/src/presets/factory.ts'))).default
  const out = []
  for (const s of f.PRESETS) out.push({ bank: 0, address: s.address, patch: s.patch })
  for (const m of f.MEMORIES) if (m.patch) out.push({ bank: 1, address: m.address, patch: m.patch })
  return out
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const all = await factory()
  const h = [
    '/* SPDX-License-Identifier: GPL-3.0-only */',
    '/* Generated by tools/gen_presets.mjs from synthex-web\'s factory bank - do not edit. */',
    '#ifndef SC_PRESETS_H', '#define SC_PRESETS_H', '#include "sc_patch.h"', '',
    `#define SC_N_PRESETS ${all.length}`,
    '/* bank (0: PRESETS, 1: MEMORIES) * 100 + the Synthex address (10..49) */',
    `static const uint16_t SC_PRESET_ADDR[SC_N_PRESETS] = { ${all.map((p) => p.bank * 100 + p.address).join(', ')} };`,
    '',
    'static const sc_patch_t SC_PRESETS[SC_N_PRESETS] = {',
    all.map((p) => patchC(p.patch)).join(',\n'),
    '};', '', '#endif', '',
  ]
  writeFileSync(join(here, '../engine/sc_presets.h'), h.join('\n'))
  console.log(`engine/sc_presets.h: ${all.length} patches`)
}
