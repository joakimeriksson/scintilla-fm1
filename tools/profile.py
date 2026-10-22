#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Where the engine's instructions go on the emulated FM-1: trace one timed block of one bench
config (fm1-emu FM1_TRACE_RANGE) and charge every instruction to its function in
build/fm1/bench.dis, and inside sx_voice_render to the source loop it belongs to.

    tools/profile.py [CONFIG]       CONFIG: an index into fm1/workload.h's WL (default 2)"""
import bisect, collections, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EMU = Path(os.environ.get("FM1_EMU", Path.home() / "work/fm1-emu/target/release/fm1-emu"))
cfg = int(sys.argv[1]) if len(sys.argv) > 1 else 2
dis = (ROOT / "build/fm1/bench.dis").read_text()

funcs = []                                       # (start address, name)
cur = None
for line in dis.splitlines():
    m = re.match(r"^([A-Za-z_][\w.]*):$", line)
    if m:
        cur = m.group(1)
        continue
    m = re.match(r"^ ([0-9a-f]{7,8}):", line)
    if m and cur and not cur.startswith((".GJT", ".L")):
        funcs.append((int(m.group(1), 16), cur))
        cur = None
funcs.sort()
starts = [a for a, _ in funcs]
mark = int(re.search(r"^bench_mark:\n\s*([0-9a-f]+):", dis, re.M).group(1), 16)

# the steps of config cfg's timed marks, then trace the first of its 16 blocks
out = subprocess.run([str(EMU), "--bin", "build/fm1/bench.bin", "--entry", "0x02000120", "--break-pc", hex(mark),
                      "--steps", "2000000000", "--quiet"], cwd=ROOT, capture_output=True, text=True,
                     env={**os.environ, "FM1_BREAK_MAX": "64"}).stdout
steps = [int(s) for s in re.findall(r"^break c0 pc=\S+ \[(\d+)\]", out, re.M)]
a, b = steps[2 * cfg], steps[2 * cfg + 1]
b = a + (b - a) // 16
tr = subprocess.run([str(EMU), "--bin", "build/fm1/bench.bin", "--entry", "0x02000120", "--steps", str(b + 10),
                     "--quiet"], cwd=ROOT, capture_output=True, text=True,
                    env={**os.environ, "FM1_TRACE_RANGE": f"{a}:{b}"}).stdout
pcs = [int(m, 16) for m in re.findall(r"^T \d+ c0 0x([0-9a-f]+)", tr, re.M)]
by_fn = collections.Counter()
by_pc = collections.Counter(pcs)
for pc in pcs:
    by_fn[funcs[bisect.bisect_right(starts, pc) - 1][1]] += 1
total = len(pcs)
print(f"config {cfg}: one block, {total:,} instructions")
for name, n in by_fn.most_common(14):
    print(f"  {name:28} {n:9,} {100 * n / total:5.1f} %")
hot = sorted(by_pc.items(), key=lambda kv: -kv[1])[:40]
(ROOT / "build/fm1/profile_pcs.txt").write_text("\n".join(f"{pc:08x} {n}" for pc, n in sorted(by_pc.items())))
