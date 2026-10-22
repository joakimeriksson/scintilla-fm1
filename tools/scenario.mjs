// SPDX-License-Identifier: GPL-3.0-only
// The scenario format both renderers read (host/sx_render.c parses the same lines):
//   dur SECONDS
//   on  T NOTE VELOCITY(0..1)
//   off T NOTE
//   joy X Y                      static stick position, -1..1 (default 0 0)
//   perf BENDOSC BENDFILT LFO2OSC LFO2FILT   the four sliders (default 0.3 0.3 0.5 0.5)
//   # a comment
export function parseScenario(text) {
  const sc = { dur: 2, events: [], joy: undefined, perf: undefined }
  for (const raw of text.split('\n')) {
    const w = raw.replace(/#.*/, '').trim().split(/\s+/).filter(Boolean)
    if (!w.length) continue
    const n = w.slice(1).map(Number)
    switch (w[0]) {
      case 'dur': sc.dur = n[0]; break
      case 'on': sc.events.push({ kind: 'on', t: n[0], note: n[1], velocity: n[2] ?? 1 }); break
      case 'off': sc.events.push({ kind: 'off', t: n[0], note: n[1] }); break
      case 'joy': sc.joy = { x: n[0], y: n[1] }; break
      case 'perf': sc.perf = { bendOsc: n[0], bendFilt: n[1], lfo2Osc: n[2], lfo2Filt: n[3] }; break
      default: throw new Error(`scenario: unknown line "${raw}"`)
    }
  }
  return sc
}
