# Scintilla — notes for working on it

synthex-web's Synthex (`~/work/ai-smarthome/audio/software-synth/synthex`) ported to integer C for the M-VAVE
FM-1. Read README.md first; this file is what the code does not say.

## The one rule

**synthex-web's `VoiceCore` is the reference** (`packages/engine/src/dsp/voice-core.ts`). Every change to
`engine/sc_voice.c` is checked by `tests/run.sh` against it, preset by preset, and must stay inside the limits
in `tools/score_all.py`. When the C engine and VoiceCore disagree, the C engine is wrong until shown otherwise.
Do not widen a limit to make a change pass; find out what moved.

Second rule: **the FM-1 plays the host's bits.** The engine is integer-only, so `fm1/run.py`'s hashes must equal
the host build's. A mismatch is a bug (in the engine, the compiler or the emulator), never noise.

## Verified

- 2026-11-01, the CPU work for fm1-dock (the two-word division, the galloping cutoff search, the mix once a
  block, the envelope-only cutoff, the per-sample cutoff's skip, the lanes and the split render): every change the
  same samples. `tests/run.sh` 320 pairs inside the limits with the scores unchanged; staged = per-sample on every
  preset and on `tests/lfo_cut.c`; `tests/udiv.c` (20 M divisions = the bit loop); `tests/split.c` (16000 blocks on
  two threads = `sc_render`); FM-1 = host on all eleven bench configs. The steady bench barely moves (Ring mod.
  51.8 -> 50.9 %); attacks do: 8-note chords struck again and again on the ROM bank's 5 ms filter attacks (a
  bench of fm1-dock's sweep, -Os -DSC_SMALL_OSC), Bass Drum - tom-toms' worst block 124.6 -> 62 % of a core, High
  Portamento 131 -> 70 %, Normal Clavinet 120 -> 57 %, Filtered strings 72 -> 64 %. fm1-dock's module renders
  half the voices on the second core: its worst factory patch ~38 % of core 0 in fm1-emu (it was 126 %).
- 2026-10-31, after the oscillators' band-limited sync and the phase-derived triangle (Metallic): level within
  0.04 dB, spectrum median 0.02 dB, 320 pairs inside the limits; staged = per-sample on every preset and on
  `tests/lfo_cut.c`; FM-1 = host on all eleven bench configs. Cost: Chunky x8 19.6 -> 19.3 %, Ring mod. 49.2 ->
  51.8 %, Sync sweep 34.8 -> 37.0 %, Fat Sound 50.7 -> 53.7 %, Metallic 54.8 -> 57.8 %, Landing 53.3 -> 56.7 %
  (the synced slave's two-sided residuals, and the per-sample path's square without the old one-call blep).
- 2026-10-31, with the 1.5 ms amp gate (`SC_AMP_ONSET_DELAY`): level within 0.05 dB, spectrum median 0.02 dB,
  320 pairs inside the limits; staged = per-sample on every preset and on `tests/lfo_cut.c`; FM-1 = host on all
  eleven bench configs. Cost: Fat Sound 49.7 -> 50.7 %, Metallic 53.9 -> 54.8 %, Landing 52.8 -> 53.3 %,
  Take-off 34.8 -> 35.1 % (the gate's test in the per-sample loop).
- 2026-10-31, after the Take-off click (cutoff tracking, no phase reset on a sounding voice, Take-off's filter
  envelope corrected in synthex-web's bank): level within 0.13 dB, spectrum median 0.02 dB, 320 pairs inside the
  limits; staged = per-sample on every preset and on `tests/lfo_cut.c`; FM-1 = host on all eleven bench configs.
  Cost: Chunky x8 18.8 -> 19.6 %, Ring mod. 47.6 -> 49.4 %, Metallic 52.7 -> 53.9 %, Landing 51.7 -> 52.8 %.
- Level within 0.09 dB, spectrum median 0.01 dB, on 80 patches x 4 scenarios (2026-10-29, after the ROM
  bank's calibration: inverted cutoff pot, measured LFO curve and depths, attack / 2, exponential release).
- The staged render (block passes) equals the per-sample one (`render_general`) bit for bit on every preset:
  `tests/run.sh` builds both (`-DSC_TEST_GENERAL`) and `cmp`s them. Only since 2026-10-31: until then run.sh
  defined `SX_TEST_GENERAL`, which nothing reads, so it compared the staged render with itself.
- FM-1 output = host output, all bench configs, with fm1-emu master of 2026-10-19.

## Ported faithfully, though they look like bugs (fix them in synthex-web first, then here)

- The LFO delay ramp restarts only when the LFO is key-synced; with sync off (every factory patch) it plays once,
  from when the voice was created.
- Every voice seeds its noise the same (`0xdeadbeef`, pink `0xfeedface`): the noise of a chord is correlated.
- A silent voice stops its 128-sample coefficient clock at the start of a run, not mid-run, so the length of the
  runs it is given is part of what it plays (the next note's first filter update moves). The app gives it 128
  (the AudioWorklet quantum); both test renderers cut runs at 128 to match. The FM-1 gives it 256.
- Since 2026-10-30 (the Take-off click) VoiceCore also recomputes the coefficients mid-block as soon as the cutoff
  has moved half a semitone (`CUTOFF_STEP`), and resets the oscillator phases only when the voice starts from
  silence; since 2026-10-31 it also starts the amp envelope 1.5 ms after the filter envelope (`AMP_ONSET_DELAY`:
  the `amp_gate` countdown here, and `sc_voice_idle` is false while it runs). The C evaluates the cutoff only on the samples where it can have moved that far: the staged render,
  while an LFO or the portamento drives it, on the samples the block's largest steps of its drivers leave room for
  (`max_step`), and by a galloping search over the block's envelope values while only the filter envelope does (the
  cutoff is monotone between the attack's peak and the next stage; `first_cross`);
  the per-sample path skips ahead by the largest step the envelope and the LFOs can take (`cut_eval`,
  `lfo_cut_dmax`: a 0.17 Hz LFO is looked at every ~1000 samples, not every one). Both update on the same
  samples, which keeps them bit-equal; `tests/lfo_cut.c` checks the LFO bound on every shape, and fails when it
  is halved.
- Since 2026-10-31 the oscillators are VoiceCore's `SyncedOsc`: hard sync restarts the slave (1 - tau) dt into
  its cycle, tau being how far after the sample OSC1 wrapped (`wrap_tau`; `S_wrap` carries it per sample in the
  staged render), and spreads the restart's step and slope change over the two samples around it with the
  PolyBLEP / PolyBLAMP residuals (`sync_now`, `blep_before/after`, `blamp_before/after`; `sc_osc_t.pend / after`
  carry the second sample's share). The triangle is `1 - 4 |phase - 1/2|` with BLAMP corners (`tri_at`), no
  longer an integrated square: that one bent instead of stepping at a sync and drifted to a DC offset of
  several times the signal on Metallic. `osc_reset` must run at init (tau = -1 means no sync pending).
- `-DSC_SMALL_OSC` (fm1-dock's module) builds the staged oscillators' synced loop for every oscillator and keeps
  the per-sample ones out of line: the same samples, a few KB less code; the SMK-37's flash map needs it.
- The chorus (2026-10-31) is fx/chorus.ts's: two lines around 4 ms swept by triangle LFOs, 0.49 Hz and 0.60 /
  4.6 Hz, per-mode wets, from the schematic of board 5860; `sc_chorus_t.ph[2]`, `CHORUS_LINES` in sc_synth.c.
- Since 2026-10-31 Q = 0.5 + 2.2 r^0.75 + 22 r^8 (`sqrt16`, an integer square root, for the 0.75 power), as
  VoiceCore's `updateCoeffs`: the recording's resonant peaks are 5-10 dB at mid settings.
- `mix.crossMod2` (OSC2 -> OSC1 PWM) is played only by `render_general`, the per-sample path. Since the ROM bank
  (2026-10-29) three presets use it (Fat Sound, Metallic, Landing), so `tests/run.sh` compares it with VoiceCore;
  it costs: Metallic's 8 voices take 53.9 % of a core (fm1/run.py), the most of any preset benched.

## Deliberate differences

- A stick move or patch edit mid-note (a new `sc_prep_t`) reaches the cutoff at the next block start, where
  VoiceCore's per-sample evaluation would catch it within half a semitone on the next sample: up to 2.9 ms.
- Aftertouch and velocity from the keys are off until SETTINGS (GLO twice) turns them on: vibrato does not suit
  every sound (Laser Harp's), so out of the box the FM-1 plays as 0.1 did.
- Aftertouch (the firmware's, not the engine's): VoiceCore has none, nor had the Synthex. The firmware turns the
  hardest press (a sensed key's, or MIDI's channel / poly pressure) into the stick pushed left beyond where it is
  set (vibrato, as CC1), so the engine only sees the stick; `SC_EV_PERF` re-preps the layers for a stick move
  without the reverb. A key's pressure under 8 (SETTINGS' FLOOR) counts as none: any vibrato switches the
  voices' per-sample pitch path on (Ring mod. x8: 53 -> 63 % of a block), and a resting finger reads a count or
  two of noise.
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

- **A fast filter envelope makes a coefficient segment of nearly every sample.** The ROM bank's 5 ms attacks sweep
  100+ semitones: past half a semitone a sample, so the staged render recomputes the coefficients (a 64 / 32
  division) and starts a segment at each sample of the attack. Whatever costs per segment or per update is paid
  ~1500 times in such a block (8 voices): the bit-loop division was a third of it, a bisection per crossing and a
  mix pass per segment another third. Keep per-segment work at loading the coefficients (`svf_pass`), and measure
  attacks, not held notes: `fm1/run.py`'s configs are steady and do not see it.
- **No statics in the voice render.** fm1-dock's module renders voices on both cores at once: the render's buffers
  are a lane (`sc_lane_t`), one per core (`SC_LANES`). A new per-render buffer goes into the lane, never into a
  `static`; `tests/split.c` (two threads, one lane each) catches one that is shared. The lanes cost one core
  ~1-2 % of itself with `SC_LANES=2` (an array's address is the lane's plus an offset, one more instruction
  where the loops are short of registers; local pointers to the arrays did not help: clang folds them back).
- **A 0.055 % constant is a bug when a parameter can be 1200.** Cents -> semitones used 655/65536 for 0.01;
  the ROM presets fold OSC2's 12-semitone transpose into its detune as 1200 cents, so OSC2 played 0.66 cents
  flat and every 1' / 2' preset beat against the reference (24 pairs failed, snr -3 dB). Now 0.01 in Q32.
- **The release is exponential** (VoiceCore's Adsr since 2026-10-29: a factor 10 per `r` seconds, idle at
  1e-4): one Q30 multiply per sample, the multiplier from `sc_exp_neg_inv`. `env_skip` steps the release
  sample by sample (one multiply each) because the per-sample truncation cannot be jumped and the staged
  render must stay bit-equal to the general one.
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
  both. The `pi32v2` lays out int64 fields differently from the Mac, so read `sc_synth_t` from a RAM dump only
  through `sc_patch_t` (int8 / int32 only, the same layout) or by symbol.
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
engine/       the synth (no float, no 64-bit division, no libc): sc_patch.h sc_fixed.h sc_voice.* sc_synth.*
              sc_tables.h (generated), sc_presets.h (decoder), sc_presets_data.h (generated)
host/         sc_render.c: scenarios on this computer
tools/        gen_tables.py gen_presets.mjs ref_render.mjs scenario.mjs compare.py score_all.py profile.py
              release.py (one round of a release: firmware/README.md), fm1_listen.py (a real FM-1 over MIDI and USB
              audio, held against the host build)
              reverb_ir.mjs reverb_check.py (the reverb against the app's impulses)
tests/        run.sh, scenarios/*.txt; udiv.c (sc_udiv64), lfo_cut.c (the cutoff skip), split.c (two lanes)
fm1/          the bench for fm1-emu: bench.c workload.h host_bench.c build.sh run.py, prim.h, trace.c;
              listen.py plays song.h (play.c / host_play.c, events from tools/song_h.py) into a WAV
firmware/     the firmware: Dinghy 0.3 (exported from upstream, GPL) + firmware/src/scintilla.c; ./build.sh,
              tests/emu_test.py (fm1-live), tests/run_host.sh. Its README says what changed in Dinghy's files
```

Factory storage: `sc_preset_load(index, &patch)` expands 25-byte records on recall;
`sc_preset_name(index)` reads the shared name pool. PRESETS are the original 200-bit Synthex
panel format; MEMORIES are exact software extension records with generated palettes.
`tools/gen_presets.mjs` retains a full-size reference in `build/preset-reference/` and checks
every decoded byte before accepting the generated data. `tests/presets_test.py` also has
independent pre-compression bank and original-ROM checksums; change them only for intentional
sound changes. `fm1/run.py` compares all 80 decoded patch hashes between target and host.
