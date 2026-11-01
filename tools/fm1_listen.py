#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Listen to a real FM-1: play presets into it over USB-MIDI, record its USB audio, and hold each take against the
same notes through the host build (host/sc_render.c, the whole instrument).
  uv run --with sounddevice --with numpy --with mido --with python-rtmidi python tools/fm1_listen.py [--keep DIR]
A take fails on silence, a dead channel, a gap in the sound (the audio interrupt overran), or a spectrum that is not
the host's. The MASTER knob is outside what is compared: every take's level is fitted, and only turned far down does
it matter. It changes the preset on the FM-1 (the last one here stays), and does not touch the flash otherwise."""
import argparse
import json
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import mido
import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parents[1]
FS = 44100
CHORD = (48, 52, 55, 60)
EIGHT = (48, 52, 55, 60, 64, 67, 72, 76)
LEAD = 0.3                                      # s of a take before its first note
EDGE = 8 / 32768                                # where a take's sound starts (a few counts: it can be a slow attack)
SOUND_DB = -70                                  # a take's peak under this: no sound, or the MASTER knob at zero
# measured on a real FM-1 (2026-11-01); spec_sync: hard sync is chaotic (CLAUDE.md), the same notes differ by this much
LIMITS = {"side": 0.5, "spec": 2.0, "spec_sync": 4.0, "shape": 3.0, "onset": 6.0, "gain_spread": 5.0}
SYNC = ("Metallic", "Ring mod.", "High Portamento")


def held(notes, off=1.5):
    return [(0, 1, n) for n in notes] + [(off, 0, n) for n in notes], off + 1.0


def struck(notes, every=0.2, n=15):
    ev = []
    for k in range(n):
        ev += [(k * every, 1, m) for m in notes] + [(k * every + every * 0.75, 0, m) for m in notes]
    return ev, n * every + 1.0


TAKES = [("Chunky Synth", 0, *held((48,))), ("Metallic", 3, *held(CHORD)), ("Ring mod.", 36, *held(EIGHT)),
         ("Brushed Cymbals", 58, *held(CHORD)), ("Take-off", 32, *held((36,), 2.0)),
         ("Bass Drum - tom-toms", 63, *struck(EIGHT)), ("High Portamento", 69, *struck(EIGHT))]


def render(preset, ev, dur, wd):
    sc = wd / "take.txt"
    sc.write_text(f"dur {dur}\n" + "".join(f"on {t} {n} 1.0\n" if on else f"off {t} {n}\n" for t, on, n in ev))
    out = wd / "take.wav"
    subprocess.run([ROOT / "build" / "sc_render", "synth", str(preset), sc, out], check=True, capture_output=True)
    with wave.open(str(out)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, 2) / 32768
    return x.astype(np.float32)


def play(port, dev, preset, ev, dur):
    """the take, from before the first note"""
    port.send(mido.Message("program_change", program=preset))
    time.sleep(2.5)                             # (the last take's reverb)
    rec = sd.rec(int((LEAD + dur + 0.3) * FS), samplerate=FS, channels=2, device=dev, dtype="float32")
    t0 = time.monotonic() + LEAD
    for t, on, n in sorted(ev, key=lambda e: e[0]):
        time.sleep(max(0, t0 + t - time.monotonic()))
        port.send(mido.Message("note_on" if on else "note_off", note=n, velocity=127 if on else 0))
    sd.wait()
    return rec


def env(x, hop=441):
    m = x.mean(axis=1)[: len(x) // hop * hop].reshape(-1, hop)
    return np.sqrt((m ** 2).mean(axis=1)) + 1e-9


def first(x, level):
    return int(np.argmax(np.abs(x).max(axis=1) >= level))


def lag(rec, ref, gain):
    """samples rec is behind ref: both start from digital silence, so by where each passes the same level"""
    return first(rec, EDGE) - first(ref, EDGE / 10 ** (gain / 20))


def bands(x):
    """third-octave levels, dB, 80 Hz .. 16 kHz"""
    m = x.mean(axis=1) * np.hanning(len(x))
    p = np.abs(np.fft.rfft(m)) ** 2
    f = np.fft.rfftfreq(len(m), 1 / FS)
    c = 80 * 2 ** (np.arange(24) / 3)
    return 10 * np.log10(np.array([p[(f >= k / 2 ** (1 / 6)) & (f < k * 2 ** (1 / 6))].sum() for k in c]) + 1e-12)


def gaps(x, lo, hi):
    """in [lo, hi), the notes held: runs of 16 samples or more that do not change, with loud sound on both sides. (A
    quiet tail, or the silence before a strike lands, is a run of zeros by itself: under 16 bits after the MASTER knob.)"""
    loud = max(np.abs(x).max() * 0.05, 0.001)
    same = np.r_[False, np.all(x[1:] == x[:-1], axis=1), False]
    edge = np.diff(same.astype(int))
    level = lambda y: np.sqrt((y ** 2).mean()) if len(y) else 0
    return sum(1 for i, j in zip(np.flatnonzero(edge == 1), np.flatnonzero(edge == -1))
               if j - i >= 16 and lo <= i < hi and level(x[i - 220:i]) > loud and level(x[j:j + 220]) > loud)


def over_time(a, b, ons):
    """dB between a and b as the sound goes on: strike by strike where it is struck (between strikes a few ms of MIDI
    decide what is loud), else every 50 ms within 20 dB of the top"""
    if len(ons) > 1:
        slots = [(int(t * FS), int(u * FS)) for t, u in zip(ons, ons[1:])]
        return np.array([20 * np.log10(np.abs(a[i:j]).max() / np.abs(b[i:j]).max()) for i, j in slots])
    ea, eb = 20 * np.log10(env(a, 2205)), 20 * np.log10(env(b, 2205))
    return (ea - eb)[eb > eb.max() - 20]


def judge(rec, ref, ev):
    g0 = (bands(rec) - bands(ref))
    k = lag(rec, ref, np.median(g0[bands(ref) > bands(ref).max() - 40]))
    n = min(len(rec) - k, len(ref))
    a, b = rec[k:k + n], ref[:n]
    first, last = min(t for t, _, _ in ev), max(t for t, _, _ in ev)
    ba, bb = bands(a), bands(b)
    use = bb > bb.max() - 40
    gain = (ba - bb)[use].mean()
    d = over_time(a, b, sorted({t for t, on, _ in ev if on}))
    body = 20 * np.log10(env(a[int(0.35 * FS):int(0.45 * FS)], 4410).max())
    return {"peak": float(20 * np.log10(np.abs(rec).max() + 1e-12)),
            "side": float(np.abs(rec).max(axis=0).min() / (np.abs(rec).max() + 1e-12)),
            "gain": float(gain), "spec": float(np.sqrt(((ba - bb - gain)[use] ** 2).mean())),
            "shape": float(np.sqrt(((d - d.mean()) ** 2).mean())),
            "gaps": gaps(rec, k + int(first * FS), k + int(last * FS)),
            "latency_ms": k / FS * 1000 - LEAD * 1000,
            "onset": float(20 * np.log10(env(a[:int(0.02 * FS)], 441).max()) - body)}


def faults(m, name):
    bad = []
    if m["peak"] < SOUND_DB:
        return [f"no sound (peak {m['peak']:.0f} dB; the MASTER knob?)"]
    if m["side"] < LIMITS["side"]:
        bad.append(f"one side quiet ({m['side']:.2f})")
    if m["gaps"]:
        bad.append(f"{m['gaps']} gaps in the sound")
    if m["spec"] > LIMITS["spec_sync" if name in SYNC else "spec"]:
        bad.append(f"spectrum {m['spec']:.2f} dB from the host's")
    if m["shape"] > LIMITS["shape"]:
        bad.append(f"level over time {m['shape']:.2f} dB from the host's")
    if name == "Take-off" and m["onset"] > LIMITS["onset"]:
        bad.append(f"a click: its onset {m['onset']:+.1f} dB over the sound after it")
    return bad


def find_fm1(wait=30):
    """its MIDI port and USB audio (a stock FM-1 has no audio input, and it takes a moment after an install)"""
    for _ in range(wait):
        sd._terminate()
        sd._initialize()
        out = [n for n in mido.get_output_names() if "Felucca" in n]
        dev = [d["name"] for d in sd.query_devices() if d["max_input_channels"] >= 2 and "Felucca" in d["name"]]
        if out and dev:
            return out, dev
        time.sleep(1)
    raise SystemExit(f"no FM-1 running Scintilla: MIDI {out}, audio {dev}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", help="a directory for the takes")
    ap.add_argument("--json", help="write the measurements here")
    a = ap.parse_args()
    (ROOT / "build").mkdir(exist_ok=True)
    translated = subprocess.run(["sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True).stdout.strip()
    arch = ["arch", "-arm64"] if translated == "1" else []      # (a Rosetta python cannot start Apple's cc)
    subprocess.run(arch + ["cc", "-O2", "-Wno-unused-function", "-o", "build/sc_render", "host/sc_render.c",
                           "engine/sc_voice.c", "engine/sc_synth.c", "-lm"], cwd=ROOT, check=True)
    out, dev = find_fm1()
    res, failed = {}, []
    with tempfile.TemporaryDirectory() as td, mido.open_output(out[0]) as port:
        wd = Path(td)
        try:
            for name, preset, ev, dur in TAKES:
                ref = render(preset, ev, dur, wd)
                rec = play(port, dev[0], preset, ev, dur)
                res[name] = judge(rec, ref, ev)
                m = res[name]
                bad = faults(m, name)
                print(f"  {'ok  ' if not bad else 'FAIL'} {name}: spectrum {m['spec']:.2f} dB, level over time "
                      f"{m['shape']:.2f} dB, {m['gaps']} gaps, level {m['gain']:+.1f} dB; {'; '.join(bad)}", flush=True)
                failed += [name] if bad else []
                if a.keep:
                    Path(a.keep).mkdir(exist_ok=True)
                    np.save(Path(a.keep) / f"{preset}.npy", rec)
                    np.save(Path(a.keep) / f"{preset}_ref.npy", ref)
        finally:
            port.send(mido.Message("control_change", control=123, value=0))
            for n in range(128):
                port.send(mido.Message("note_off", note=n))
    gains = [m["gain"] for m in res.values()]
    if max(gains) - min(gains) > LIMITS["gain_spread"]:
        print(f"  FAIL the takes' levels differ by {max(gains) - min(gains):.1f} dB (one MASTER knob, one gain)")
        failed.append("level")
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))
    print("all passed" if not failed else "failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
