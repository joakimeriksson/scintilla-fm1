# Changelog

## 0.2.0 (2026-11-01)

Identity `FM-1_96300200`. Everything here follows [synthex-web](https://github.com/joakimeriksson/ai-smarthome/tree/master/audio/software-synth/synthex),
the reference, and is checked against it (`tests/run.sh`).

**The sound**

- The ROM bank: the 40 PRESETS now carry the values decoded from the Synthex's own EPROMs, with envelope reach, LFO
  pitch depth and PWM depth measured on a recording of the real instrument. Many sounds change.
- The chorus as the schematic has it: two bucket-brigade lines, triangle LFOs at 0.49 Hz and 0.60 / 4.6 Hz.
- Band-limited hard sync, a phase-derived triangle, VoiceCore's resonance curve.
- An exponential release, and the falling ramp as an LFO shape (RAMP-).
- Take-off starts without its click: its filter envelope is corrected, the cutoff is followed within a block, and a
  voice retriggered while it sounds keeps its oscillator phases.
- The amp envelope starts 1.5 ms after the filter envelope.

**The firmware**

- Velocity and aftertouch from the FM-1's own keys, on a SETTINGS page (GLO twice); off until you turn them on.
- MIDI CC 7 is the volume. The DIN jack's UART is latched as in Dinghy 0.4.
- A page with Install on my FM-1: <https://joakimeriksson.github.io/scintilla-fm1/>.
- Releases are built and signed on GitHub by the Firmware Hub's shared workflow.

**The cost**

- Fast filter attacks are about half as dear: eight voices struck again and again on the heaviest patches went from
  ~125 % of a core to ~70 % (-Os, as fm1-dock builds it). This firmware renders on one core; fm1-dock's module shares the voices between two.
- The cutoff tracking and the new oscillators cost a few points on held chords: Metallic 52.7 -> 56.8 %, Ring mod.
  47.6 -> 50.9 %.

**Fixed in the tests:** `tests/run.sh` never compared the staged render with the per-sample one (a misspelt define);
it does now, and they are equal on every preset.

## 0.1.1 (2026-10-23)

0.1 with its own identity: `FM-1_96300101` (0.1 reported `FM-1_960`, which SID-1 also uses).

## 0.1 (2026-10-23)

The first release: the 80 factory sounds on the FM-1, two layers of 8 voices, chorus, an algorithmic reverb, the
knobs and pages, MIDI over USB and the DIN jack.
