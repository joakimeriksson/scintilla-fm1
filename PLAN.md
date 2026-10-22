# Plan

## Done (2026-10-21)

- **E1 Engine port.** VoiceCore, the voice pool (poly / mono / unison), layers (single / split / double), chorus,
  limiter; the factory bank converted mechanically. Checked against VoiceCore (`tests/run.sh`).
- **E2 On the FM-1's CPU.** Bit-identical to the host in fm1-emu; 8 voices of the heaviest factory patch at 49 % of
  a core, a plain one at 20 %.

- **F1 A firmware** (2026-10-21): on Dinghy 0.3 (`firmware/`): the 80 presets on PRESETS, 12 pages of four
  parameters on the knobs, the joystick on SELECT / ALGORITHM, USB and DIN MIDI, the CPU on the screen.
  `tests/emu_test.py` passes in fm1-emu: the firmware's note is the engine's to -60 dB, Ring mod. x8 at 49 %.

## Next

1. **Hardware** (only with the user): install `firmware/build/scintilla.fwsc` on a real FM-1. Unknowns there: the
   CPU with flash (XIP) cache misses (the emulator counts instructions; Ring mod. x8 is at 49 % of them), the DIN
   jack's UART driver (Dinghy's, marked untested on hardware), the identity FM-1_96N against the hub's list.
2. **Saving sounds.** A flash range for user patches (widen `FL_RANGE_OK`), SAVE to write the edited sound; the
   parameter table in `scintilla.c` could also drive a scenario `set PATH VALUE` (step 5).
3. **Delay.** A delay of ~0.5 s per side in int16 (the factory bank uses up to 0.52 s). (The reverb is done:
   an 8-line feedback network, `tools/reverb_check.py`.)
4. **Cost.** Ring mod. is the worst patch (52 % with its reverb, 49 % without): per-sample pitch during its glide (`sc_pitch_inc` each sample),
   the LFO loop, the cross-modulated pulse. Options: pitch at control rate (every 8-16 samples) during glides —
   measure the difference against VoiceCore first; specialise the LFO loop per shape. The second core is free.
5. **Test the untested.** A scenario line `set PATH VALUE` (both renderers) to reach what no factory patch uses:
   OSC2 -> OSC1 cross mod, pink noise, the LFO shapes beyond triangle, velocity routes.
