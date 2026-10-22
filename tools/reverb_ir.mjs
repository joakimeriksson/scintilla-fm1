// SPDX-License-Identifier: GPL-3.0-only
// The app's reverb impulse, as the ConvolverNode plays it: synthex-web's own SynthReverb.buildIR
// (packages/engine/src/fx/reverb.ts) on a stand-in context, then the scale Chrome gives a convolver's
// impulse (normalize = true, Blink's reverb.cc: 1 / rms over both channels, times -58 dB, times
// 44100 / rate). Stereo float32, interleaved.
//
//   node --experimental-transform-types tools/reverb_ir.mjs ALGO SIZE DAMP OUT.f32
//   ALGO 0..3 (plate room hall galactic, sx_patch.h's order), SIZE DAMP 0..1
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { SYNTHEX } from './gen_presets.mjs'

const [algo, size, damp, out] = process.argv.slice(2)
const { SynthReverb } = await import(join(SYNTHEX, 'packages/engine/src/fx/reverb.ts'))
const ALGO = ['plate', 'room', 'hall', 'galactic'][+algo]
const RECIPES = { plate: [0.6, 2.5], room: [0.3, 1.4], hall: [1.2, 4.5], galactic: [3.0, 9.0] }  // setParams'
const sr = 44100
const ctx = {
  sampleRate: sr,
  createBuffer: (n, len) => { const ch = Array.from({ length: n }, () => new Float32Array(len)); return { getChannelData: (c) => ch[c], ch } },
}
const [base, max] = RECIPES[ALGO]
const ir = SynthReverb.prototype.buildIR.call({ ctx }, ALGO, base + +size * (max - base), +damp)
const [l, r] = ir.ch
let p = 0
for (const c of [l, r]) for (const v of c) p += v * v
const scale = (1 / Math.max(Math.sqrt(p / (2 * l.length)), 0.000125)) * 10 ** (-58 / 20) * (44100 / sr)
const o = new Float32Array(2 * l.length)
for (let i = 0; i < l.length; i++) { o[2 * i] = l[i] * scale; o[2 * i + 1] = r[i] * scale }
writeFileSync(out, Buffer.from(o.buffer))
