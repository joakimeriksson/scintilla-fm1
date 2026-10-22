#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Scintilla on the emulated FM-1, end to end (fm1-emu's fm1-live, headless):
    ./build.sh && tests/emu_test.py
Each case boots build/scintilla.fwsc with a key / encoder / MIDI script (tests/emu.py) and checks the
sound, and the firmware's own state in a RAM dump at the end (by symbol, from build/scintilla.syms).
FM1_LIVE: fm1-live (default ~/work/fm1-emu/target/release/fm1-live); fm1-emu is next to it."""
import os, re, struct, subprocess, sys, tempfile
from pathlib import Path
import numpy as np

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC / "tests"))
import emu  # noqa: E402

OUT = SRC / "build" / "emu"
RAM_BASE = 0x01C00000
FS = 44100
failures = []
# sc_patch_t has int8 and int32 fields only, so its layout is the same here and on the FM-1
PATCH_NAME, LAYER0, CUTOFF = 0, 28, None


def check(case, ok, why):
    print(f"  {'ok  ' if ok else 'FAIL'} {case}: {why}")
    if not ok:
        failures.append(case)


def native(tool):
    """Apple's cc / git shims, natively: a Rosetta-translated python (an x86-64 conda on Apple silicon)
    starts their x86-64 slice, which cannot load its own libxcrun"""
    t = subprocess.run(["sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True).stdout.strip()
    return ["arch", "-arm64", tool] if t == "1" else [tool]


def cc():
    return native("cc")


def sym(name):
    m = re.search(r"^([0-9a-f]{8}) .*\s" + re.escape(name) + r"$", (SRC / "build" / "scintilla.syms").read_text(), re.M)
    return int(m.group(1), 16) - RAM_BASE


def patch_offsets():
    """offsets in sc_patch_t, by the host's compiler (the same layout as the FM-1's: see above)"""
    c = SRC / "build" / "offsets.c"
    c.write_text('#include <stdio.h>\n#include <stddef.h>\n#include "sc_patch.h"\nint main(void){printf("%zu %zu\\n",'
                 ' offsetof(sc_patch_t, layer[0].cutoff), sizeof(sc_patch_t));}\n')
    exe = SRC / "build" / "offsets"
    subprocess.run([*cc(), "-I", str(SRC.parent / "engine"), "-o", str(exe), str(c)], check=True)
    return [int(x) for x in subprocess.run([str(exe)], capture_output=True, text=True).stdout.split()]


def engine_ref():
    exe = SRC / "build" / "engine_ref"
    e = SRC.parent / "engine"
    subprocess.run([*cc(), "-O2", "-I", str(e), "-o", str(exe), str(SRC / "tests" / "engine_ref.c"),
                    str(e / "sc_voice.c"), str(e / "sc_synth.c")], check=True)
    return exe


def stereo(s):
    return np.array(s, dtype=float).reshape(-1, 2)


def peak(s, t0, t1):
    return max((abs(x) for x in s[int(t0 * FS) * 2:int(t1 * FS) * 2]), default=0)


def fresh_check():
    """fm1-live and fm1-emu built from their checkout as it is: an older binary misses what the
    emulator has learnt since (an fm1-live of 2026-10-12 halted on a clz that master runs)"""
    root = emu.LIVE.parents[2]
    head = subprocess.run([*native("git"), "-C", str(root), "log", "-1", "--format=%ct"], capture_output=True, text=True).stdout.strip()
    if not head:
        return check("fresh", True, f"{root} is not a git checkout: not checked")
    old = [p.name for p in (emu.LIVE, emu.LIVE.with_name("fm1-emu")) if p.stat().st_mtime < int(head)]
    check("fresh", not old, "fm1-live and fm1-emu are newer than their checkout's last commit" if not old else
          f"{', '.join(old)} older than {root}'s last commit: cargo build --release -p fm1-live -p fm1-emu")


def decode_check():
    """every instruction of the build through fm1-emu's own decoder (--check-decode): what the emulator
    cannot run fails here, not mid-test"""
    fe = emu.LIVE.with_name("fm1-emu")
    line = re.compile(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*\t(.*)$")
    rows = [(m.group(2).split(), m.group(3).strip()) for m in map(line.match, (SRC / "build" / "scintilla.dis").read_text().splitlines())
            if m and not m.group(3).startswith("<")]
    text = "\n".join("".join(b + (rows[i + 1][0] if i + 1 < len(rows) else ["00", "00"])) for i, (b, _) in enumerate(rows))
    with tempfile.NamedTemporaryFile("w", suffix=".txt") as f:
        f.write(text + "\n")
        f.flush()
        out = subprocess.run([str(fe), "--check-decode", f.name], capture_output=True, text=True).stdout.splitlines()
    if len(out) != len(rows):
        return check("decode", False, f"{fe} has no --check-decode (an fm1-emu older than 2026-10-19?)")
    never = {"wfe", "sevl", "sevg", "trigger"}
    bad = sorted({asm for (b, asm), o in zip(rows, out) if o.split("|")[-1] != "ok" and asm.split()[0] not in never})
    check("decode", not bad, f"{len(rows)} instructions, all known to the emulator" if not bad
          else f"unknown to the emulator: {', '.join(bad[:6])}")


def main():
    global CUTOFF
    CUTOFF, psize = patch_offsets()
    fresh_check()
    decode_check()

    # a key on the first preset (Chunky Synth); the sound, then the engine's own render of it
    s, _ = emu.run("1000:21,1800:21^", 2600, OUT / "boot")
    check("boot", peak(s, 0.0, 0.7) == 0 and peak(s, 0.85, 1.5) > 1000,
          f"silent until the key, then it plays (peak {peak(s, 0.85, 1.5)})")
    e = stereo(s)
    on = int(np.argmax(np.abs(e[:, 0]) > 0))
    st, n = on - on % 256 - 256, 256 * 24                     # the note's block (the attack's first is ~0)
    a = e[st:st + n]
    ref = engine_ref()
    best = (0.0, 0, 0.0)
    for k in range(on // 256 - 40, on // 256 + 20):          # how long the synth ran before the note
        h = stereo(np.frombuffer(subprocess.run([str(ref), str(k), "24", "60", "0"], capture_output=True).stdout, np.int16))
        g = float((a * h).sum() / (h * h).sum())
        r = a - g * h
        err = 10 * np.log10((r * r).sum() / (a * a).sum())
        if err < best[0]:
            best = (err, k, g)
    check("engine", best[0] < -50, f"the FM-1's note is the engine's, {best[0]:.1f} dB under it (the MASTER knob's "
          f"rounding; gain {best[2]:.3f}, {best[1]} blocks after the start)")

    # PRESETS 36 detents: Ring mod.; eight keys; KNOB1 on HOME is the cutoff
    keys = ",".join(f"1200:{k}" for k in (14, 16, 18, 21, 23, 25, 28, 30))
    s, _ = emu.run(f"500:e6:36,{keys},2000:e2:-5", 3000, OUT / "ring", ram=True)
    ram = (OUT / "ring" / "ram.bin").read_bytes()
    syn, staged, cpu = sym("syn"), sym("staged"), sym("cpu_pub")
    name = ram[staged:staged + 28].split(b"\0")[0].decode()
    check("preset", name == "Ring mod.", f"PRESETS +36 loads {name!r}")
    cut = struct.unpack_from("<i", ram, syn + CUTOFF)[0]
    want = struct.unpack_from("<i", ram, staged + CUTOFF)[0] - 5 * 655
    check("knob", cut == want, f"KNOB1 -5 on HOME: cutoff {cut / 65536:.3f} (the preset's - 0.05)")
    ticks = struct.unpack_from("<I", ram, cpu)[0]
    pct = 100 * ticks / (256 * 1_000_000 // FS * 24)
    check("cpu", 0 < pct < 70, f"eight voices of Ring mod.: the slowest render of the last second {pct:.0f} % of a block")
    check("chord", peak(s, 1.35, 2.8) > 1000, f"the chord sounds (peak {peak(s, 1.35, 2.8)})")

    # MIDI into the DIN jack: a program change (29, Vibes), a note
    s, _ = emu.run("800:mc01d,1200:m903c64,1900:m803c00", 2600, OUT / "midi", ram=True)
    ram = (OUT / "midi" / "ram.bin").read_bytes()
    name = ram[staged:staged + 28].split(b"\0")[0].decode()
    check("midi", name == "Vibes" and peak(s, 1.05, 1.8) > 1000, f"program change 29 -> {name!r}; a note plays "
          f"(peak {peak(s, 1.05, 1.8)})")

    print(f"{len(failures)} failed" if failures else "all passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
