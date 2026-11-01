#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build the ROM panel records and exact software-MEMORIES extension.

Called by gen_presets.mjs with its full-size C reference bank. The ROM format
is the Synthex's 200 bits, in reverse byte order as stored at $D000. MEMORIES
use separate, generated per-word palettes in 25-byte extension records: they
contain settings (LP12, LFO2, FX) the hardware format cannot express.

Raw ROM parameters: synthex-web/tools/synthex-rom/data/rom_presets_raw.json,
decoded from the T41 EPROM with its own 6502 recall routine. Mapping/curves:
synthex-web/tools/synthex-rom/gen_factory.py (2026-10-31 calibration).
The extension palettes belong to this generated factory bank, not a stable
serialization format for saved user sounds.
"""
import json
from pathlib import Path
import struct
import subprocess
import sys
from host_cc import host_cc

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = [8] * 9 + [7] * 8 + [4] * 9 + [6] + [3] * 4 + [2] * 9


def panel_pack(params):
    value = shift = 0
    for i, (p, width) in enumerate(zip(params, WIDTHS)):
        scaled = 9 <= i < 26 or i >= 34
        v = p >> (8 - width) if scaled else p
        assert (v << (8 - width) if scaled else v) == p
        assert 0 <= v < 1 << width
        value |= v << shift
        shift += width
    assert shift == 200 and len(params) == 40
    return value.to_bytes(25, 'little')[::-1]


def emit(ctype, name, values, columns=12):
    rows = [', '.join(map(str, values[i:i + columns])) for i in range(0, len(values), columns)]
    return f'static const {ctype} {name}[{len(values)}] = {{\n    ' + ',\n    '.join(rows) + '\n};\n'


def main():
    reference = Path(sys.argv[1]).resolve()
    work = reference.parent
    export = work / 'export.c'
    export.write_text('''#include <stdio.h>
#include <stddef.h>
#include "sc_presets.h"
int main(void) {
 printf("%zu %zu %zu %zu %d\\n", sizeof(sc_patch_t), sizeof(sc_layer_t),
 offsetof(sc_patch_t, layer), offsetof(sc_patch_t, voice_mode), SC_N_PRESETS);
 fwrite(SC_PRESETS, sizeof SC_PRESETS, 1, stdout);
}
''')
    cc = host_cc()
    subprocess.run(cc + ['-I', str(reference.parent), '-I', str(ROOT / 'engine'),
                        str(export), '-o', str(work / 'export')], check=True)
    header, raw = subprocess.check_output([str(work / 'export')]).split(b'\n', 1)
    psize, lsize, loff, tailoff, count = map(int, header.split())
    assert (psize, lsize, loff, tailoff, count) == (620, 256, 28, 540, 80), 'update codec layout'
    patches = [raw[i:i + psize] for i in range(0, len(raw), psize)]
    for p in patches:
        assert p[loff:loff + lsize] == p[loff + lsize:tailoff], 'distinct layers need a codec extension'
    rom = json.loads((ROOT / 'tools/data/synthex_rom.json').read_text())
    records = [panel_pack(p) for p in rom]
    vectors = [struct.unpack('<84I', p[loff:loff + lsize] + p[tailoff:]) for p in patches[40:]]
    palettes = [list(dict.fromkeys(c)) for c in zip(*vectors)]
    widths = [(len(t) - 1).bit_length() for t in palettes]
    assert sum(widths) <= 200, f'MEMORIES extension needs {sum(widths)} bits; extend record format'
    for vector in vectors:
        value = shift = 0
        for v, table, width in zip(vector, palettes, widths):
            value |= table.index(v) << shift
            shift += width
        records.append(value.to_bytes(25, 'little'))
    names, offsets = bytearray(), []
    for p in patches:
        offsets.append(len(names))
        names.extend(p[:loff].split(b'\0')[0] + b'\0')
    starts, pool = [0], []
    for table in palettes:
        pool.extend(table)
        starts.append(len(pool))
    # Preserve the decimal rounding of gen_factory.py before Q16 conversion.
    # Tables keep exp/pow/float and 64-bit division out of the target decoder.
    decimal = lambda v, n: int(round(float(f'{v:.{n}f}') * 10 ** n))
    env_ms = [3.102, 6.204, 14.52, 29.04, 36.96, 73.92, 99, 198,
              257.4, 514.8, 660, 1320, 1782, 3564, 6600, 13200]
    tables = [
        emit('uint16_t', 'SC_ROM_ENV_MS', [decimal(v / 1000, 3) for v in env_ms]),
        emit('uint16_t', 'SC_ROM_ATTACK_MS', [decimal(v / 1000 * .5, 3) for v in env_ms]),
        emit('uint16_t', 'SC_ROM_RATE_CHZ', [decimal(27.7 * 400 ** (-v / 255), 2) for v in range(256)]),
        emit('uint16_t', 'SC_ROM_DELAY_CS', [decimal(0 if 255 - v < 12 else .001 * 30000 ** ((255 - v) / 255), 2) for v in range(256)]),
        emit('uint16_t', 'SC_ROM_GLIDE_MS', [decimal(.005 * 200 ** (1 - v / 254), 3) for v in range(0, 256, 2)]),
        emit('uint16_t', 'SC_ROM_ENV_MILLI', [decimal(.58 * 1.25 * 255 / 60 * (v / 255), 3) for v in range(256)]),
        emit('uint16_t', 'SC_ROM_ENV_LONG_MILLI', [decimal(.58 * 1.25 * 255 / 60 * (v / 255) * .6, 3) for v in range(256)]),
        emit('uint16_t', 'SC_ROM_PITCH_1E4', [decimal(.09 * ((255 - v) / 255) / max(.05, v / 255), 4) for v in range(256)]),
    ]
    text = ['/* SPDX-License-Identifier: GPL-3.0-only */',
            '/* Generated by tools/gen_presets.mjs + pack_presets.py; do not edit. */',
            '#ifndef SC_PRESETS_DATA_H', '#define SC_PRESETS_DATA_H',
            '#define SC_N_PRESETS 80', '#define SC_PRESET_RECORD_BYTES 25',
            'static const uint8_t SC_PRESET_RECORDS[80][25] = {',
            *['    { ' + ', '.join(map(str, r)) + ' },' for r in records], '};',
            emit('uint16_t', 'SC_PRESET_ADDR', [bank * 100 + address for bank in range(2) for address in range(10, 50)]),
            emit('uint16_t', 'SC_PRESET_NAME_OFF', offsets),
            emit('char', 'SC_PRESET_NAMES', list(names)),
            emit('uint16_t', 'SC_MEM_PALETTE_OFF', starts),
            emit('uint32_t', 'SC_MEM_VALUES', [f'0x{v:08x}u' for v in pool], 8),
            *tables, '#endif', '']
    (ROOT / 'engine/sc_presets_data.h').write_text('\n'.join(text))
    print(f'80 x 25-byte records; MEMORIES use {sum(widths)}/200 bits; {len(pool)} extension palette words')


if __name__ == '__main__':
    main()
