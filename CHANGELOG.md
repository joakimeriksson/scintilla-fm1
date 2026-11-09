# Changelog

## Unreleased

**The sound**

- The oscillators reach the mixer and the ring modulator through a 5 Hz coupling, as synthex-web's now do: a narrow
  pulse's DC (2 pw - 1 of it) no longer thumps under every note (Brass II, Funky Clav., Electric piano I, the
  clavichords, Metallic piano, Pianet, Sweep 1). It costs ~18 instructions a voice-sample: Chunky Synth x8 19 -> 22 %
  of a core, Ring mod. x8 51 -> 54 %.
- The ROM bank, as synthex-web's retune: full key tracking is 1.0 semitone per key (it was 0.81), and the filter
  envelope's sustain 0.7 of its knob. Measured on held notes at the start of each preset's passage in the
  run-through; the organs, Pianet, Ceilos, Double basses and Brass II gain most, Electric piano II loses.
- Filtered chorus's filter envelope at 0.7 of its decoded amount: its notes open 12-15 semitones less, as on the
  run-through.

**The firmware**

- Every parameter the engine plays is on a page now (26 pages, 90 parameters), as PROPHET's in fm1-dock: a row for
  each knob, its name, its value and a bar. HOME keeps its columns and the keys.
- A page button held for 0.4 s goes back a page; the screen shows where in the group you are.
- LAYERS: edit the upper, the lower or both layers; make a sound single, split (at a note) or double; its voices.
- The sustain pedal (MIDI CC 64, the Synthex's HOLD), from USB and the DIN jack.
- CC 71 resonance, CC 72 release and CC 73 attack (both envelopes), as PROPHET's; CC 70 the cutoff.
- On fm1-dock's SMK-37: FADER BANK gives its faders (CC 70..73) PLAY, FILTER ENV, AMP ENV or MIX; KNOB BANK picks
  the layers the knobs edit; < > step through every page.
- The OUTPUT page's TUNE knob is gone: neither the engine nor synthex-web plays the master tune.
- The pages are numbered anew: the page saved by 0.1 or 0.2 opens as the same page.
- The pitch routes (LFO to OSC 1 / OSC 2, ENV1 to OSC 2) turn by ratios and show three decimals under 0.1: the
  presets' vibratos are 0.005..0.04.
- Fixed: the stick turned right (ALGORITHM, or STICK X) did not reach the sound since 0.2's aftertouch: LFO 2 into
  the filter did nothing.

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
