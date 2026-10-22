// SPDX-License-Identifier: GPL-3.0-only
// The reference: render a scenario through synthex-web's own VoiceCore (via its offline renderer,
// tools/compare/render.ts) at 44.1 kHz, as raw float32 mono. host/sc_render.c renders the same
// scenario through the C port; tools/compare.py scores the pair.
//
//   node --experimental-transform-types tools/ref_render.mjs PRESET SCENARIO OUT.f32 [--nudge]
//   PRESET: an index into the bank as gen_presets.mjs orders it, or `all` (OUT is then a
//   directory and each preset goes to OUT/<index>.f32)
//   --nudge: bend the pitch by 5e-5 semitone, a few Q16 steps of the C engine's pitch. A second take
//   with it is the measurement's floor (tests/run.sh): it differs from the first by VoiceCore's
//   random OSC1 noise and by how much the preset magnifies an inaudible pitch error. Hard sync
//   magnifies it a lot: Sync. Harmonic Sweep moves 0.8 dB in spectrum from that nudge alone.
//
// The loop is render.ts's (events on the first sample at or after their time, runs between them)
// with runs cut at 128 samples as the AudioWorklet runs it, written out here so the nudge can reach
// VoiceCore. host/sc_render.c cuts its runs the same way.
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { SYNTHEX_WEB, factory } from './gen_presets.mjs'
import { parseScenario } from './scenario.mjs'

const args = process.argv.slice(2).filter((a) => !a.startsWith('--'))
const nudge = process.argv.includes('--nudge') ? 5e-5 : 0
const [idx, scenFile, outFile] = args
const { VoiceCore } = await import(join(SYNTHEX_WEB, 'packages/engine/src/dsp/voice-core.ts'))
const bank = await factory()
const sc = parseScenario(readFileSync(scenFile, 'utf8'))

function render(patch) {
  const sr = 44100, n = Math.floor(sc.dur * sr), out = new Float32Array(n)
  const core = new VoiceCore(sr, patch)
  if (sc.perf) core.setPerformance(sc.perf)
  if (sc.joy) core.setJoy(sc.joy.x, sc.joy.y)
  if (nudge) core.setPitchBend(nudge)
  const ev = [...sc.events].sort((a, b) => a.t - b.t)
  let e = 0, i = 0
  while (i < n) {
    while (e < ev.length && ev[e].t <= i / sr) {
      if (ev[e].kind === 'on') core.noteOn(ev[e].note, ev[e].velocity ?? 1)
      else core.noteOff()
      e++
    }
    const next = e < ev.length ? Math.min(n, Math.max(i + 1, Math.ceil(ev[e].t * sr))) : n
    // runs of at most 128, the AudioWorklet's quantum: VoiceCore checks for silence only at the
    // start of a run, so this is what the app plays (render.ts's longer runs keep a silent voice's
    // coefficient clock running and move the next note's first filter update)
    for (; i < next; i += Math.min(128, next - i)) core.render(out, i, Math.min(128, next - i))
  }
  return out
}

function one(i, file) {
  const entry = bank[i]
  if (!entry) throw new Error(`no preset ${i} (0..${bank.length - 1})`)
  const out = render(JSON.parse(JSON.stringify(entry.patch.upper)))
  writeFileSync(file, Buffer.from(out.buffer, out.byteOffset, out.byteLength))
}

if (idx === 'all') bank.forEach((_, i) => one(i, join(outFile, `${i}.f32`)))
else one(Number(idx), outFile)
