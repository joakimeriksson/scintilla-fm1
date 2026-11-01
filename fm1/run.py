#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The engine's CPU cost on the emulated FM-1 (after fm1-emu/fm1-sid/fm1/run.py).

    fm1/run.py [--opt -O2|-Os] [--no-build]

Builds fm1/bench.c (fm1/build.sh), runs it in fm1-emu with a break on bench_mark, and reads the
instruction counts between the marks: per 256-frame block, which is what app_audio() gets 5.8 ms
for. Instructions are not cycles: the % of a 240 MHz core assumes one per cycle (pi32v2 issues one
most of the time; XIP loads and divides take longer), so read it as a lower bound. The hashes must
equal the host build's (fm1/host_bench.c): the engine is integer, so the FM-1 plays the same bits.
FM1_EMU: the emulator (default ~/work/fm1-emu/target/release/fm1-emu)."""
import os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EMU = Path(os.environ.get("FM1_EMU", Path.home() / "work/fm1-emu/target/release/fm1-emu"))
RES = 0x01C80000
FS, MHZ, BLOCK = 44100, 240, 256
BUDGET = MHZ * 1e6 * BLOCK / FS                     # instructions in one block's 5.8 ms


def workload():
    src = (ROOT / "fm1/workload.h").read_text()
    rows = re.findall(r'\{ "([^"]+)",\s*(\d+),\s*(\d+),\s*(\d+) \}', src)
    blocks = int(re.search(r"#define WL_BLOCKS (\d+)", src).group(1))
    return [(w, int(p), int(v), int(d)) for w, p, v, d in rows], blocks


def cc():
    """cc, natively: a Rosetta-translated python (an x86-64 conda on Apple silicon) would start
    the x86-64 slice of Apple's cc shim, which cannot load its own libxcrun"""
    t = subprocess.run(["sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True).stdout.strip()
    return ["arch", "-arm64", "cc"] if t == "1" else ["cc"]


def host_hashes():
    exe = ROOT / "build/host_bench"
    subprocess.run([*cc(), "-O2", "-o", str(exe), "fm1/host_bench.c", "engine/sc_voice.c", "engine/sc_synth.c"],
                   cwd=ROOT, check=True)
    return [int(h, 16) for h in subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split()]


def main():
    args = sys.argv[1:]
    opt = args[args.index("--opt") + 1] if "--opt" in args else "-O2"
    if "--no-build" not in args:
        subprocess.run([str(ROOT / "fm1/build.sh"), opt], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    dis = (ROOT / "build/fm1/bench.dis").read_text()
    m = re.search(r"^([0-9a-f]+) <bench_mark>:|^bench_mark:\n\s*([0-9a-f]+):", dis, re.M)
    mark = int(m.group(1) or m.group(2), 16)
    configs, blocks = workload()
    out = subprocess.run([str(EMU), "--bin", "build/fm1/bench.bin", "--entry", "0x02000120",
                          "--break-pc", hex(mark), "--steps", "2000000000", "--quiet",
                          "--dump", hex(RES), str(1024 + 80)],
                         cwd=ROOT, capture_output=True, text=True,
                         env={**os.environ, "FM1_BREAK_MAX": str(2 * len(configs) + 1)})
    steps = [int(s) for s in re.findall(r"^break c0 pc=\S+ \[(\d+)\]", out.stdout, re.M)]
    mem = []
    for line in out.stdout.splitlines():
        m = re.match(r"\s+0x([0-9a-f]+): (.*)", line)
        if m:
            mem += [int(w, 16) for w in m.group(2).split()]
    if len(steps) < 2 * len(configs) or not mem or mem[0] != 0x42465853:  # (the bench halts itself)
        sys.exit(f"the bench did not finish:\n{out.stdout[-1500:]}\n{out.stderr[-1500:]}")
    want = host_hashes()
    patch_hashes = [int(h, 16) for h in subprocess.check_output([str(ROOT / "build/host_bench"), "presets"], text=True).split()]
    if mem[1024:1024 + 80] != patch_hashes:
        sys.exit("decoded factory patches differ between FM-1 and host")
    print("All 80 decoded factory patches: FM-1 = host, byte hashes equal.\n")
    print(f"Scintilla engine on the emulated FM-1 (pi32v2 {opt}), {FS} Hz, {MHZ} MHz, one core;")
    print(f"a block is {BLOCK} frames = {BUDGET:,.0f} instructions of budget (half of it is the safe line).\n")
    print(f" {'config':30} {'voices':>6} {'instr/block':>12} {'per voice-sample':>17} {'% of a core':>12}  = host")
    ok = True
    for i, (what, preset, voices, dbl) in enumerate(configs):
        per = (steps[2 * i + 1] - steps[2 * i]) / blocks
        nv = voices * (2 if dbl else 1)
        same = mem[2 + i] == want[i]
        ok &= same
        print(f" {what:30} {nv:6} {per:12,.0f} {per / BLOCK / nv:17.0f} {per / BUDGET * 100:11.1f} %  "
              f"{'yes' if same else 'NO'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
