# Scintilla (Synthex FM-1) — notes for working on it

The synthex-web Synthex (`~/work/ai-smarthome/audio/software-synth/synthex`) ported to integer C for the M-VAVE
FM-1. Read README.md first; this file is what the code does not say.

## The one rule

**synthex-web's `VoiceCore` is the reference** (`packages/engine/src/dsp/voice-core.ts`). Every change to
`engine/sx_voice.c` is checked by `tests/run.sh` against it, preset by preset, and must stay inside the limits
in `tools/score_all.py`. When the C engine and VoiceCore disagree, the C engine is wrong until shown otherwise.
Do not widen a limit to make a change pass; find out what moved.

Second rule: **the FM-1 plays the host's bits.** The engine is integer-only, so `fm1/run.py`'s hashes must equal
the host build's. A mismatch is a bug (in the engine, the compiler or the emulator), never noise.

## Verified

- Level within 0.21 dB, spectrum median 0.02 dB, on 80 patches x 4 scenarios (2026-10-21).
- The staged render (block passes) equals the per-sample one (`render_general`) bit for bit on every preset:
  `tests/run.sh` builds both (`-DSX_TEST_GENERAL`) and `cmp`s them.
- FM-1 output = host output, all bench configs, with fm1-emu master of 2026-10-19.

## Ported faithfully, though they look like bugs (fix them in synthex-web first, then here)

- The LFO delay ramp restarts only when the LFO is key-synced; with sync off (every factory patch) it plays once,
  from when the voice was created.
- Every voice seeds its noise the same (`0xdeadbeef`, pink `0xfeedface`): the noise of a chord is correlated.
- A silent voice stops its 128-sample coefficient clock at the start of a run, not mid-run, so the length of the
  runs it is given is part of what it plays (the next note's first filter update moves). The app gives it 128
  (the AudioWorklet quantum); both test renderers cut runs at 128 to match. The FM-1 gives it 256.
- `mix.crossMod2` (OSC2 -> OSC1 PWM) is in no factory patch, so `render_general`, the only path that plays it,
  is never compared with VoiceCore. Test it (a scenario that sets a parameter) before trusting it.

## Deliberate differences

- One phase per oscillator, where VoiceCore keeps one per waveform: they differ only if the waveform changes
  mid-note.
- Pitch is Q16 semitones (resolution 1.5e-5); portamento runs in Q32 and the glide offsets in Q24, because in Q16 a
  slow portamento's per-sample step rounds to zero and stalls ~0.7 semitone short (found by the comparison).
- The limiter is the app's DynamicsCompressor curve (threshold -3, knee 6, ratio 12, makeup +1.65 dB, 3 / 150 ms,
  5.8 ms look-ahead) in log2 units, decided every 16 samples. Not measured against Chrome's.
- The reverb is not the app's convolution (noise impulses up to 9 s) but an 8-line feedback delay network with
  its statistics: decay time, damping lowpass, energy (Chrome's -58 dB impulse scaling), L/R uncorrelated; one for
  both layers. `tools/reverb_check.py` measures it against synthex-web's own `buildIR` for every algorithm at three
  sizes and dampings (2026-10-22: level within 0.17 dB, RT60 within 1 %, spectrum at the two-draws noise floor; a
  -4 dB notch in the 100 Hz band remains). Its gain has one fitted term (the first pass out of the lines). It costs
  ~205 instructions a sample (3.8 % of a core): Ring mod. x8 went from 48.6 % to 52.3 %. The delay is not ported.

## Gotchas that cost time

- **Headroom after the voices.** A layer's bus (the voices summed, before the volume) passes 1.0 on loud chords
  (Brass I's stabs: 1.8). The chorus line was int16 Q15, clamped at 1.0: its wet half clipped 20 dB under the
  signal on every attack (found by ear in the video, 2026-10-22). Anything that stores the bus keeps Q20 in int32.

- **An old fm1-emu runs this engine wrong.** The binary of 2026-10-12 left the filter's state stuck (a 64-bit
  multiply-accumulate); master of 2026-10-19 runs it right. When the FM-1 and host disagree, rebuild the emulator
  before suspecting the code. `fm1/prim.h` tests the arithmetic primitives one by one; `fm1/trace.c` traces a
  voice's insides sample by sample on both.
- **Hidden helper calls break the FM-1 link:** a 64-bit division (`__udivdi3`), even by a constant, and also
  `u / (12 << 16)` became a hardware divide where a table is cheaper. `fm1/build.sh` fails on the first; look at
  `build/fm1/bench.dis` for the second.
- fm1-emu reports only 8 break hits unless `FM1_BREAK_MAX` says more, and runs to `--steps` after the program ends:
  the bench ends by jumping to address 0, which halts it.
- The firmware's audio is the engine's to -60 dB (the MASTER knob's rounding) only if the reference has run as many
  idle blocks as the firmware before the note: the chorus LFO runs freely from boot. Without that, the match ends
  after two blocks (the chorus's 12 ms delay) and looks like a broken engine. `tests/emu_test.py` searches for it.
- A stale emulator binary looks like a broken firmware. An fm1-live of 2026-10-12 halted on the dual-issue `clz`
  (`80 f1 00 DS`) that master decodes since 2026-10-15 (and a stale fm1-emu once gave wrong bench hashes).
  `tests/emu_test.py` fails when fm1-live or fm1-emu is older than the fm1-emu checkout's last commit; rebuild
  with `cargo build --release -p fm1-live -p fm1-emu` (only `target/` changes).
- `tests/emu.py`'s `ms:mHEX` MIDI goes into the DIN jack (fm1-live has no scripted USB-MIDI): the firmware reads
  both. The `pi32v2` lays out int64 fields differently from the Mac, so read `sx_synth_t` from a RAM dump only
  through `sx_patch_t` (int8 / int32 only, the same layout) or by symbol.
- fm1-emu's `--ram` must stay at or under 4 MiB: RAM starts at 0x01C00000, so more covers the code at
  0x02000000, the CPU fetches zeros, and the run "halts on a nop slide" after a few thousand steps.
- A Rosetta python (x86-64 conda) cannot start Apple's `cc` shim: `fm1/run.py` uses `arch -arm64 cc` then.
- synthex-web's TypeScript needs `node --experimental-transform-types` (parameter properties), not strip-types.
- Hard sync makes the comparison chaotic: 5e-5 semitone moves the spectrum ~0.8 dB. That is why the reference is
  rendered twice, nudged (`--nudge`), and the limits sit on that floor.
- Register pressure is the pi32v2's cost, not arithmetic (a 64-bit multiply is one instruction). One loop doing a
  whole voice spilled ~120 values a sample; the staged render (control, OSC1, OSC2, mix, filter passes) halved the
  cost. `tools/profile.py N` traces one block of bench config N in fm1-emu and charges every instruction to its
  function.

## Layout

```
engine/       the synth (no float, no 64-bit division, no libc): sx_patch.h sx_fixed.h sx_voice.* sx_synth.*
              sx_tables.h (generated) sx_presets.h (generated)
host/         sx_render.c: scenarios on this computer
tools/        gen_tables.py gen_presets.mjs ref_render.mjs scenario.mjs compare.py score_all.py profile.py
              reverb_ir.mjs reverb_check.py (the reverb against the app's impulses)
tests/        run.sh, scenarios/*.txt
fm1/          the bench for fm1-emu: bench.c workload.h host_bench.c build.sh run.py, prim.h, trace.c;
              listen.py plays song.h (play.c / host_play.c, events from tools/song_h.py) into a WAV
firmware/     the firmware: Dinghy 0.3 (exported from upstream, GPL) + firmware/src/synthex.c; ./build.sh,
              tests/emu_test.py (fm1-live), tests/run_host.sh. Its README says what changed in Dinghy's files
```
