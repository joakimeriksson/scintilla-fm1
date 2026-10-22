#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Score every build/cmp/<scenario>/<i>.f32 (VoiceCore) against c<i>.f32 (the C engine).

The limits hold above the measurement's own floor: <scenario>/again/<i>.f32 is a second VoiceCore
take with the pitch nudged by 5e-5 semitone. It is a different noise where OSC1 is noise (VoiceCore
seeds that from Math.random), and a different waveform where the preset magnifies tiny pitch
errors (hard sync); for anything else it is the same to a few hundredths of a dB. The C take may
differ from the reference by about as much as the two references do: the limit is LIMIT + 1.5 floor."""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from compare import score
import numpy as np

LEVEL_DB = 0.25        # rms level difference
SPEC_DB = 0.5          # mean |spectrum difference|

root = Path(sys.argv[1])
names = subprocess.run(["build/sc_render", "list"], capture_output=True, text=True).stdout.splitlines()
rows, bad = [], 0
for d in sorted(p for p in root.iterdir() if p.is_dir()):
    for ref in sorted(d.glob("[0-9]*.f32"), key=lambda p: int(p.stem)):
        i = int(ref.stem)
        a = np.fromfile(ref, "<f4")
        r = score(a, np.fromfile(d / f"c{i}.f32", "<f4"))
        fl = score(a, np.fromfile(d / "again" / f"{i}.f32", "<f4"))
        r.update(scenario=d.name, preset=i, name=names[i][4:].strip(),
                 floor_spec=fl["spec"], floor_level=abs(fl["level"]))
        r["ok"] = bool(abs(r["level"]) <= LEVEL_DB + 1.5 * r["floor_level"]
                   and r["spec"] <= SPEC_DB + 1.5 * r["floor_spec"])
        bad += not r["ok"]
        rows.append(r)
(root / "scores.json").write_text(json.dumps(rows, indent=1))
rows.sort(key=lambda r: -(abs(r["level"]) / (LEVEL_DB + 1.5 * r["floor_level"])
                          + r["spec"] / (SPEC_DB + 1.5 * r["floor_spec"])))
print(f"{'scenario':8} {'preset':34} {'level':>7} {'spec':>6} {'floor':>6} {'snr':>6} {'peak ref/c':>12}")
for r in rows[:20]:
    print(f"{r['scenario']:8} {r['name'][:34]:34} {r['level']:+7.2f} {r['spec']:6.2f} {r['floor_spec']:6.2f} "
          f"{r['snr']:6.1f} {r['peak_ref']:5.2f}/{r['peak_c']:5.2f} {'' if r['ok'] else 'FAIL'}")
lv = np.array([abs(r["level"]) for r in rows]); sp = np.array([r["spec"] for r in rows])
print(f"\n{len(rows)} pairs: level |diff| median {np.median(lv):.3f} max {lv.max():.2f} dB; "
      f"spectrum median {np.median(sp):.3f} max {sp.max():.2f} dB; {bad} outside the limits")
sys.exit(1 if bad else 0)
