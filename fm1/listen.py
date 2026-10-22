#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Play a song on the emulated FM-1 and listen to it.

    fm1/listen.py [OUT.wav] [--opt -O2] [--part PRESET:SCENARIO ...]

Writes the song's event table (tools/song_h.py), builds fm1/play.c (fm1/build.sh), runs it in
fm1-emu, dumps the PCM it rendered into RAM and writes it as a 16-bit stereo WAV (default
build/listen/fm1-emu.wav). The same song is rendered by fm1/host_play.c on this computer, and the
two must be equal sample for sample. Without --part it plays a tour of four presets. The
FM-1's RAM holds 20.8 s of it.
FM1_EMU: the emulator (default ~/work/fm1-emu/target/release/fm1-emu)."""
import os, re, subprocess, sys, time, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fm1"))
from run import EMU, RES, cc  # noqa: E402

PCM = RES + 16                               # fm1/play.c
RAM = 4 << 20                                # the most fm1-emu can have below the code
SC = "tests/scenarios"
TOUR = [f"0:{SC}/chords.txt", f"36:{SC}/phrase.txt", f"41:{SC}/phrase.txt", f"77:{SC}/phrase.txt"]


def main():
    args = sys.argv[1:]
    opt = args.pop(args.index("--opt") + 1) if "--opt" in args else "-O2"
    if "--opt" in args: args.remove("--opt")
    parts = []
    while "--part" in args:
        k = args.index("--part")
        parts.append(args.pop(k + 1)); args.pop(k)
    out = Path(args[0]) if args else ROOT / "build/listen/fm1-emu.wav"
    (ROOT / "build/fm1").mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "tools/song_h.py", "build/fm1/song_ev.h", *(parts or TOUR)], cwd=ROOT, check=True)
    subprocess.run([str(ROOT / "fm1/build.sh"), opt], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)

    exe = ROOT / "build/host_play"
    subprocess.run([*cc(), "-O2", "-o", str(exe), "fm1/host_play.c", "engine/sc_voice.c", "engine/sc_synth.c"],
                   cwd=ROOT, check=True)
    want = subprocess.run([str(exe)], check=True, capture_output=True).stdout
    frames = len(want) // 4
    if PCM + 4 * frames > 0x01C00000 + RAM:
        sys.exit(f"the song is {frames / 44100:.1f} s; the FM-1's RAM holds {(0x01C00000 + RAM - PCM) / 4 / 44100:.1f} s")

    t0 = time.time()
    run = subprocess.run([str(EMU), "--bin", "build/fm1/play.bin", "--entry", "0x02000120", "--ram", str(RAM),
                          "--steps", "4000000000", "--quiet", "--dump", hex(RES), str(4 + frames)],
                         cwd=ROOT, capture_output=True, text=True)
    secs = time.time() - t0
    words = []
    for line in run.stdout.splitlines():
        m = re.match(r"\s+0x([0-9a-f]+): (.*)", line)
        if m:
            words += m.group(2).split()
    if len(words) < 4 or int(words[0], 16) != 0x4C505853 or int(words[1], 16) != frames:
        sys.exit(f"the song did not finish on the emulator:\n{run.stdout[-1500:]}\n{run.stderr[-1500:]}")
    got = b"".join(int(w, 16).to_bytes(4, "little") for w in words[4:])
    if len(got) != len(want):
        sys.exit(f"the emulator gave {len(got)} bytes, wanted {len(want)}:\n{run.stdout[-1500:]}\n{run.stderr[-1500:]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100); w.writeframes(got)
    same = got == want
    diff = next((i for i in range(0, len(got), 4) if got[i:i + 4] != want[i:i + 4]), None)
    print(f"{out}: {frames / 44100:.1f} s played on the emulated FM-1 in {secs:.0f} s of emulation")
    print("  equal to this computer's render, sample for sample" if same
          else f"  DIFFERS from this computer's render from frame {diff // 4}")
    sys.exit(0 if same else 1)


main()
