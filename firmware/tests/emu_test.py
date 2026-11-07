#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Scintilla on the emulated FM-1, end to end (fm1-emu's fm1-live, headless):
    ./build.sh && tests/emu_test.py
Each case boots build/scintilla.fwsc with a key / encoder / MIDI script (tests/emu.py) and checks the
sound, and the firmware's own state in a RAM dump at the end (by symbol, from build/scintilla.syms).
FM1_LIVE: fm1-live (default ~/work/fm1-emu/target/release/fm1-live); fm1-emu is next to it."""
import os, re, struct, subprocess, sys, tempfile, zlib
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


# Every knob of every page, as the page table has them (firmware/src/scintilla.c PAGE): the group's button,
# then for each page its four fields (in sc_patch_t, or "perf." in sc_perf_t; None: a knob this test leaves alone)
L0 = "layer[0]."
PAGES = [
    (8, [[L0 + "cutoff", L0 + "reso", L0 + "env_amt", L0 + "env_a.r"]]),
    (6, [[L0 + "o1_wave", L0 + "o1_oct", L0 + "o1_pwm", L0 + "mix_o1"],
         [L0 + "o2_wave", L0 + "o2_oct", L0 + "o2_detune", L0 + "mix_o2"],
         [L0 + "o2_pwm", L0 + "o2_sync", L0 + "cross", L0 + "cross2"],
         [L0 + "mix_noise", L0 + "noise_pink", L0 + "ring", None],
         [None, "voice_mode", "split", "polyphony"]]),
    (4, [[L0 + "flt_mode", L0 + "cutoff", L0 + "reso", L0 + "key_track"],
         [L0 + "env_amt", L0 + "mm[SC_MM_E1_CUT]", L0 + "mm[SC_MM_VEL_CUT]", L0 + "mm[SC_MM_JY_CUT]"],
         [L0 + "env_f.a", L0 + "env_f.d", L0 + "env_f.s", L0 + "env_f.r"],
         [L0 + "env_a.a", L0 + "env_a.d", L0 + "env_a.s", L0 + "env_a.r"],
         [L0 + "mm[SC_MM_E1_P2]", L0 + "mm[SC_MM_VEL_AMP]", None, None]]),
    (5, [*[pg for k, m in ((0, 1), (1, 2)) for pg in (
            [L0 + f"lfo[{k}].rate", L0 + f"lfo[{k}].shape", L0 + f"lfo[{k}].delay", L0 + f"lfo[{k}].sync"],
            [L0 + f"mm[SC_MM_L{m}_P1]", L0 + f"mm[SC_MM_L{m}_P2]", L0 + f"mm[SC_MM_L{m}_CUT]", L0 + f"mm[SC_MM_L{m}_AMP]"],
            [L0 + f"mm[SC_MM_L{m}_PW1]", L0 + f"mm[SC_MM_L{m}_PW2]", L0 + f"lfo[{k}].depth_a", L0 + f"lfo[{k}].depth_b"])],
         ["perf.lfo2_osc", "perf.lfo2_filt", L0 + "mm[SC_MM_JX_L1]", L0 + "mm[SC_MM_JX_L2]"]]),
    (7, [[L0 + "glide_mode", L0 + "glide_amt", L0 + "glide_time", L0 + "key_assign"],
         [None, None, None, None],
         [L0 + "glide_o1", L0 + "glide_o2", L0 + "multi_trigger", "unison_detune"],
         [L0 + "o1_glide_amt", L0 + "o1_glide_speed", L0 + "o2_glide_amt", L0 + "o2_glide_speed"]]),
    (2, [["fx.chorus.on", "fx.chorus.rate", "fx.chorus.depth", "fx.chorus.mix"],
         ["fx.reverb.on", "fx.reverb.size", "fx.reverb.damping", "fx.reverb.mix"],
         ["volume", "limiter", None, None]]),
    (3, [["perf.joy_x", "perf.joy_y", "perf.bend_osc", "perf.bend_filt"]]),
]


def fields(names):
    """{name: (offset, size, the first preset's value)} by the host's compiler (sc_patch_t and sc_perf_t are int8
    and int32 only: the FM-1's layout)"""
    c = SRC / "build" / "fields.c"
    rows = []
    for n in names:
        if n == "sizeof patch":                 # (where syn.perf starts: right after syn.patch)
            rows.append('printf("%zu 0 0\\n", sizeof(sc_patch_t));')
            continue
        ty, f, var = ("sc_perf_t", n[5:], "q") if n.startswith("perf.") else ("sc_patch_t", n, "p")
        rows.append(f'printf("%zu %zu %d\\n", offsetof({ty}, {f}), sizeof {var}.{f}, (int)({var}.{f}));')
    c.write_text('#include <stdio.h>\n#include <stddef.h>\n#include "sc_presets.h"\n#include "sc_synth.h"\n'
                 'int main(void){sc_patch_t p; sc_perf_t q; sc_preset_load(0, &p); sc_perf_default(&q);\n'
                 + "\n".join(rows) + "}\n")
    exe = SRC / "build" / "fields"
    e = SRC.parent / "engine"
    subprocess.run([*cc(), "-I", str(e), "-o", str(exe), str(c), str(e / "sc_synth.c"), str(e / "sc_voice.c")], check=True)
    out = subprocess.run([str(exe)], capture_output=True, text=True).stdout.split("\n")
    return {n: tuple(int(x) for x in ln.split()) for n, ln in zip(names, out)}


def pages_check():
    """turn each knob of each page one detent (down, or up from 0), on the first preset: each field moves (the
    layer's in the upper, which a single patch edits; MODE makes it split, and from then on both). The stick's in
    the engine's copy (syn.perf), the one it plays (the stick turned right, STICK X up from 0, must stay there)"""
    names = [n for _, pgs in PAGES for pg in pgs for n in pg if n]
    fs = fields(sorted(set(names)) + ["sizeof patch"])
    ev, t = [], 400
    for btn, pgs in PAGES:
        for pg in pgs:
            ev += [f"{t}:{btn}", f"{t + 60}:{btn}^"]
            t += 200
            for k, n in enumerate(pg):
                if n:
                    ev.append(f"{t}:e{2 + k}:{-1 if fs[n][2] else 1}")
                    t += 120
    _, _ = emu.run(",".join(ev), t + 400, OUT / "pages", ram=True)
    ram = (OUT / "pages" / "ram.bin").read_bytes()
    syn = sym("syn")
    still = []
    for n in sorted(set(names)):
        off, size, was = fs[n]
        base = syn + fs["sizeof patch"][0] if n.startswith("perf.") else syn
        now = int.from_bytes(ram[base + off:base + off + size], "little", signed=True)
        if now == was:
            still.append(n)
    check("pages", not still, f"{len(set(names))} fields on {sum(len(p) for _, p in PAGES)} pages, each moved by its knob"
          if not still else f"not moved by their knob: {', '.join(still)}")


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

    # the keys' force (fm1-live's pills: ID@VEL lands a key at a velocity, ID~VEL presses it to another's
    # force): off at first (the keys play at 100, pressing harder does nothing); SETTINGS (GLO twice)
    # turns TOUCH (KNOB1) and VELO (KNOB4) on: a soft landing's velocity, then pressing harder is
    # aftertouch, the stick pushed left (vibrato): the sound is the soft press's until then and moves
    # after it; easing off lets it go
    at, st = sym("at_applied"), sym("set")
    off, _ = emu.run("1000:20@50,1300:20~127", 2000, OUT / "at_off", ram=True)
    ram = (OUT / "at_off" / "ram.bin").read_bytes()
    check("settings_off", ram[at] == 0 and ram[st + 3] == 0 and ram[st + 6] == 0,
          f"at first TOUCH and VELO are off: pressed harder, the stick at {ram[at]} / 127")
    on = "200:7,300:7^,400:7,500:7^,600:e2:1,650:e5:1,"
    soft, _ = emu.run(on + "1000:20@50", 2000, OUT / "at_soft", ram=True)
    ram = (OUT / "at_soft" / "ram.bin").read_bytes()
    vel = ram[sym("key_vel") + 6]
    check("settings", ram[st + 1] == 19 and ram[st + 3] == 1 and ram[st + 6] == 1,
          f"GLO twice: page {ram[st + 1]} (SETTINGS); TOUCH {ram[st + 3]}, VELO {ram[st + 6]}")
    hard, _ = emu.run(on + "1000:20@50,1300:20~127", 2000, OUT / "at_hard", ram=True)
    a_hard = (OUT / "at_hard" / "ram.bin").read_bytes()[at]
    eased, _ = emu.run(on + "1000:20@50,1300:20~127,1600:20~50", 2000, OUT / "at_eased", ram=True)
    a_eased = (OUT / "at_eased" / "ram.bin").read_bytes()[at]
    h, w = stereo(hard), stereo(soft)
    onset = int(np.argmax(np.any(w != 0, axis=1)))          # the note (the recording starts after the boot)
    diff = np.nonzero(np.any(h != w, axis=1))[0]
    apart = (diff[0] - onset) / FS if len(diff) else -1      # the press harder is 0.3 s after the landing
    r, ref = h[onset + int(0.5 * FS):] - w[onset + int(0.5 * FS):], w[onset + int(0.5 * FS):]
    moved = 10 * np.log10((r * r).sum() / max(1e-9, (ref * ref).sum()))
    check("velocity", 30 < vel < 80, f"a key landed at 50's force plays at velocity {vel}")
    check("aftertouch", a_hard == 127 and a_eased == 0 and 0.2 < apart < 0.4 and moved > -20,
          f"pressed harder: the stick at {a_hard} / 127 (eased off: {a_eased}); the sound the soft press's until "
          f"{apart:.3f} s after the landing, {moved:.1f} dB away after it")
    s, _ = emu.run(on + "1000:m903c64,1300:md07f", 1800, OUT / "at_midi", ram=True)
    a_midi = (OUT / "at_midi" / "ram.bin").read_bytes()[at]
    check("midi_pressure", a_midi == 127, f"MIDI channel pressure 127: the stick at {a_midi} / 127")

    # the sustain pedal (CC 64) into the DIN jack: a note let go under it sounds on until the pedal comes up; a
    # note struck again under it takes a second voice, and the pedal's release lets both go
    def held(script, name):
        s, _ = emu.run(script, 4200, OUT / name, ram=True)
        return s, (OUT / name / "ram.bin").read_bytes()
    free, _ = held("800:m903c64,1200:m803c00", "sus_none")
    ped, ram = held("700:mb0407f,800:m903c64,1200:m803c00,1500:m903c64,1700:m803c00,2600:mb04000", "sus_pedal")
    sus = sym("sus_offs")
    check("sustain", peak(ped, 2.0, 2.5) > 10 * max(1, peak(free, 2.0, 2.5)) and peak(ped, 3.7, 4.1) < 60
          and not any(ram[sus:sus + 128]),
          f"after the note-off: {peak(ped, 2.0, 2.5)} with the pedal, {peak(free, 2.0, 2.5)} without; 1.1 s after the "
          f"pedal is up (two voices of the note): {peak(ped, 3.7, 4.1)}")

    # the pedal over USB (fm1-live's FM1_USB_SEND, the screen's run: RAM only): down, a note and its note-off, the
    # note-off held back; then up, none left
    sus_on, sus_n = sym("sustain"), sym("sus_offs") + 0x3C
    usb = "1500:b0407f;1600:903c64;1800:803c00"
    _, _ = emu.run("", 2200, OUT / "sus_usb", ram=True, usb=usb)
    down = (OUT / "sus_usb" / "ram.bin").read_bytes()
    _, _ = emu.run("", 2400, OUT / "sus_usb_up", ram=True, usb=usb + ";2100:b04000")
    up = (OUT / "sus_usb_up" / "ram.bin").read_bytes()
    check("sustain_usb", down[sus_on] == 1 and down[sus_n] == 1 and up[sus_on] == 0 and up[sus_n] == 0,
          f"CC64 over USB: the pedal {down[sus_on]}, the note-off held back {down[sus_n]}; up: {up[sus_on]}, {up[sus_n]}")

    # an older version's settings (the record's length tells which): its page by its number here, 0.2's SETTINGS (10)
    # on 19, 0.1's OUTPUT (10, before SETTINGS was) on 24; the rest of the record as it was
    img = OUT / "flash.bin"
    img.unlink(missing_ok=True)
    emu.run("", 300, OUT / "flash", flash=img)
    base = img.read_bytes()
    got = []
    for rec, want in ((bytes([3, 10, 1, 1, 50, 9, 1]), 19), (bytes([3, 10, 1]), 24)):
        f = bytearray(base)
        f[0xFC000:0xFD000] = b"\xff" * 0x1000
        f[0xFC000:0xFC00C + len(rec)] = struct.pack("<3I", 0x59474E44, len(rec), zlib.crc32(rec)) + rec
        img.write_bytes(bytes(f))
        _, _ = emu.run("", 600, OUT / "flash", ram=True, flash=img)
        ram = (OUT / "flash" / "ram.bin").read_bytes()
        got.append((len(rec), ram[st + 1], want, ram[st:st + len(rec)] == bytes(rec[:1]) + bytes([want]) + rec[2:]))
    check("settings_old", all(g[1] == g[2] and g[3] for g in got),
          "; ".join(f"{n}-byte record: page {p} (want {w}){'' if ok else ', the rest moved'}" for n, p, w, ok in got))

    # a group's button: pressed again, the next page; held 0.4 s, the one before; held while another group's is
    # pressed, that one's page stays (EDIT is 1..5, ENV 6..10)
    pg = []
    for name, script in (("next", "200:6,300:6^,400:6,500:6^"), ("back", "200:6,300:6^,400:6,1000:6^"),
                         ("other", "200:6,300:6^,400:6,500:4,600:4^,1100:6^")):
        _, _ = emu.run(script, 1300, OUT / f"grp_{name}", ram=True)
        pg.append((OUT / f"grp_{name}" / "ram.bin").read_bytes()[st + 1])
    check("page_buttons", pg == [2, 5, 6], f"EDIT again: page {pg[0]} (want 2); held: {pg[1]} (5); held, ENV pressed: "
          f"{pg[2]} (6)")

    # a change of the voices' routing (LAYERS' VOICES here) releases what sounds: a note held (never let go) dies
    # away after it, and plays on without it
    lay = "800:m903c64,1000:6,1060:6^,1200:6,1260:6^,1400:6,1460:6^,1600:6,1660:6^,1800:6,1860:6^"
    kept, _ = emu.run(lay, 4200, OUT / "route_none")
    cut, _ = emu.run(lay + ",2000:e5:-1", 4200, OUT / "route_voices")
    check("routing", peak(kept, 3.6, 4.1) > 10 * max(1, peak(cut, 3.6, 4.1)),
          f"a note held, VOICES turned on LAYERS: {peak(cut, 3.6, 4.1)} 1.6 s later, {peak(kept, 3.6, 4.1)} without")

    # CC 71 / 72 / 73: resonance, both envelopes' release and attack
    _, _ = emu.run("700:mb04740,800:mb0487f,900:mb04900", 1400, OUT / "cc", ram=True)
    ram = (OUT / "cc" / "ram.bin").read_bytes()
    fs = fields([L0 + "reso", L0 + "env_a.r", L0 + "env_f.r", L0 + "env_a.a", L0 + "env_f.a"])
    v = {n: struct.unpack_from("<i", ram, sym("syn") + o)[0] for n, (o, _, _) in fs.items()}
    want = {L0 + "reso": 64 * 516, L0 + "env_a.r": 15 << 16, L0 + "env_f.r": 15 << 16, L0 + "env_a.a": 65, L0 + "env_f.a": 65}
    check("cc", all(abs(v[n] - want[n]) <= want[n] // 16 for n in want),
          "CC71 64, CC72 127, CC73 0: " + ", ".join(f"{n[len(L0):]} {v[n] / 65536:.3f}" for n in want))

    pages_check()

    print(f"{len(failures)} failed" if failures else "all passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
