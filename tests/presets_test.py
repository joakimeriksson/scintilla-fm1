#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check native ROM bytes and exact expansion of all factory sounds.

By default uses the original bank's SHA-256, independent of synthex-web.
--reference HEADER additionally compares each byte against a freshly generated
full-size reference. Generation runs this automatically and fails on drift.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
# Captured from the pre-compression bank; includes every field and padding byte.
# Update only for intentional sound/name changes, after the reference check.
PATCH_SHA256 = 'a70ad50882259e08b2120eab52cd352771604a92f9bdd39559c533f38c530401'
ROM_SHA256 = 'a3b49f9ace62011cc5b2b1b0a18e5aa18ff74a392450944ef5cc56fd3f291593'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path)
    args = parser.parse_args()
    out = ROOT / 'build/preset-test'
    out.mkdir(parents=True, exist_ok=True)
    reference = ''
    if args.reference:
        reference = '''
#undef SC_PRESETS_H
#define SC_PRESETS REFERENCE
#define SC_PRESET_ADDR REFERENCE_ADDR
#include "''' + str(args.reference.resolve()) + '''"
'''
    source = '''#include <stdio.h>
#include <string.h>
#include "sc_presets.h"
''' + reference + '''
int main(int argc, char **argv) {
 if (argc > 1 && !strcmp(argv[1], "rom")) {
  fwrite(SC_PRESET_RECORDS, 25, 40, stdout); return 0;
 }
 for (unsigned i = 0; i < SC_N_PRESETS; i++) {
  sc_patch_t p;
  memset(&p, 0xa5, sizeof p);
  sc_preset_load(i, &p);
  if (strcmp(p.name, sc_preset_name(i))) return 2;
  if (i == 0) { sc_patch_t q; sc_preset_load(SC_N_PRESETS, &q); if (memcmp(&p, &q, sizeof p)) return 3; }
'''
    if args.reference:
        source += '''
  if (SC_PRESET_ADDR[i] != REFERENCE_ADDR[i] || memcmp(&p, &REFERENCE[i], sizeof p)) {
   fprintf(stderr, "preset %u (%s) differs from reference\\n", i, p.name); return 1;
  }
'''
    source += '  fwrite(&p, sizeof p, 1, stdout);\n }\n return 0;\n}\n'
    (out / 'test.c').write_text(source)
    cc = ['arch', '-arm64', 'cc'] if sys.platform == 'darwin' else ['cc']
    subprocess.run(cc + ['-O2', '-Wall', '-Wextra', '-Wno-unused-function',
                        '-fsanitize=undefined,address', '-I', str(ROOT / 'engine'),
                        str(out / 'test.c'), '-o', str(out / 'test')], check=True)
    decoded = subprocess.check_output([str(out / 'test')])
    if not args.reference:
        assert hashlib.sha256(decoded).hexdigest() == PATCH_SHA256, 'factory sound changed'
    rom = subprocess.check_output([str(out / 'test'), 'rom'])
    assert hashlib.sha256(rom).hexdigest() == ROM_SHA256, 'original ROM records changed'
    print('presets: 80 exact expansions; 40 original ROM records; sanitizers passed')


if __name__ == '__main__':
    main()
