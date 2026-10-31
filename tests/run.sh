#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Every preset through every scenario, in VoiceCore (the reference) and in the C engine; scores
# per pair in build/cmp/scores.json and a summary; then the reverb against the app's
# (tools/reverb_check.py). Fails if a pair is outside the limits in tools/score_all.py, or the reverb
# outside its own. The reference is rendered twice, the second take nudged by 5e-5 semitone
# (tools/ref_render.mjs --nudge): the two differ by the measurement's own floor for that preset.
set -e
cd "$(dirname "$0")/.."
mkdir -p build
cc -O2 -Wall -Wextra -Wno-unused-function -o build/sc_render host/sc_render.c engine/sc_voice.c engine/sc_synth.c -lm
cc -O2 -Wno-unused-function -DSC_TEST_GENERAL -o build/sc_render_general host/sc_render.c engine/sc_voice.c engine/sc_synth.c -lm
# the per-sample path's skipped samples (cut_eval) against the staged render, over every LFO shape on the cutoff
cc -O2 -Wall -Wextra -Wno-unused-function -o build/lfo_cut tests/lfo_cut.c engine/sc_voice.c engine/sc_synth.c -lm
cc -O2 -Wno-unused-function -DSC_TEST_GENERAL -o build/lfo_cut_general tests/lfo_cut.c engine/sc_voice.c engine/sc_synth.c -lm
./build/lfo_cut > build/lfo_cut.txt
./build/lfo_cut_general | cmp -s - build/lfo_cut.txt || { echo "staged != general: tests/lfo_cut.c"; exit 1; }
n=$(./build/sc_render list | wc -l | tr -d ' ')
for sc in tests/scenarios/*.txt; do
    name=$(basename "$sc" .txt)
    mkdir -p "build/cmp/$name"
    mkdir -p "build/cmp/$name/again"
    node --experimental-transform-types --no-warnings tools/ref_render.mjs all "$sc" "build/cmp/$name"
    node --experimental-transform-types --no-warnings tools/ref_render.mjs all "$sc" "build/cmp/$name/again" --nudge
    i=0
    while [ "$i" -lt "$n" ]; do
        ./build/sc_render voice "$i" "$sc" "build/cmp/$name/c$i.f32"
        # the staged render (block passes) must be the per-sample one, bit for bit
        ./build/sc_render_general voice "$i" "$sc" "build/cmp/$name/g$i.f32"
        cmp -s "build/cmp/$name/c$i.f32" "build/cmp/$name/g$i.f32" || { echo "staged != general: preset $i, $name"; exit 1; }
        i=$((i + 1))
    done
done
status=0
python3 tools/score_all.py build/cmp || status=$?
# the reverb: not sample for sample (the app's is noise), so by what it measures (tools/reverb_check.py)
python3 tools/reverb_check.py build/reverb || status=$?
# the renders are ~700 MB: kept only with KEEP=1 (scores.json stays)
[ "${KEEP:-0}" = 1 ] || for sc in tests/scenarios/*.txt; do rm -rf "build/cmp/$(basename "$sc" .txt)"; done
exit $status
