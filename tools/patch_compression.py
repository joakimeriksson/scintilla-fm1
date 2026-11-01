#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure lossless factory-bank encodings without changing firmware.

Run: python3 tools/patch_compression.py
Uses the host C compiler to export the actual bank/layout; only build/ is written.
All experimental compressed records are decoded and compared byte for byte.
Numbers include names, address table, record offsets and data dictionaries,
but exclude decoder machine code and linker alignment.
"""
import argparse
import collections
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib
from host_cc import host_cc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'firmware/tools'))
import lz4blk


def words(data):
    return list(struct.unpack('<' + 'I' * (len(data) // 4), data))


def unwords(values):
    return struct.pack('<' + 'I' * len(values), *values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-dir', type=Path, default=ROOT / 'engine')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'build/patch-compression')
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = out / 'export.c'
    source.write_text('''#include <stdio.h>
#include <stddef.h>
#include "sc_presets.h"
int main(void) {
 printf("%zu %zu %zu %zu %zu %zu %d\\n", sizeof(sc_patch_t), sizeof(sc_layer_t),
 offsetof(sc_patch_t, layer), offsetof(sc_patch_t, voice_mode),
 sizeof(sc_fx_p_t), offsetof(sc_patch_t, fx), SC_N_PRESETS);
#ifdef SC_PRESET_RECORD_BYTES
 for (unsigned i = 0; i < SC_N_PRESETS; i++) { sc_patch_t p; sc_preset_load(i, &p); fwrite(&p, sizeof p, 1, stdout); }
#else
 fwrite(SC_PRESETS, sizeof(SC_PRESETS), 1, stdout);
#endif
}
''')
    cc = host_cc()
    subprocess.run(cc + ['-I', str(args.engine_dir.resolve()), str(source), '-o', str(out / 'export')], check=True)
    header, raw = subprocess.check_output([str(out / 'export')]).split(b'\n', 1)
    psize, lsize, loff, tailoff, fxsize, fxoff, count = map(int, header.split())
    patches = [raw[i:i + psize] for i in range(0, len(raw), psize)]
    assert len(patches) == count and tailoff == loff + 2 * lsize
    layers = [p[loff + k * lsize:loff + (k + 1) * lsize] for p in patches for k in range(2)]
    unique = list(dict.fromkeys(layers))
    names = [p[:loff].split(b'\0')[0] + b'\0' for p in patches]
    tails = [p[tailoff:] for p in patches]
    name_cost = sum(map(len, names)) + 2 * (count + 1)
    addresses = count * 2
    rows = {}

    def record(label, size):
        rows[label] = {'bytes': size, 'saving_percent': round(100 * (1 - size / (len(raw) + addresses)), 2)}

    def compressed_records(records):
        blocks = [lz4blk.compress(r) for r in records]
        for block, original in zip(blocks, records):
            assert lz4blk.decompress(block) == original
        assert sum(map(len, blocks)) < 65536
        return sum(map(len, blocks)) + 2 * (len(records) + 1)

    record('Current structs + addresses', len(raw) + addresses)
    record('Raw unique layers + raw tails + packed names', len(unique) * lsize + 2 * count + sum(map(len, tails)) + name_cost + addresses)
    record('LZ4 independent full patches', compressed_records(patches) + addresses)
    record('LZ4 whole bank (full-bank RAM required)', compressed_records([raw]) + addresses)
    record('DEFLATE whole bank (comparison only)', len(zlib.compress(raw, 9)) + addresses)
    record('LZ4 unique layers + independent tails + names', compressed_records(unique) + 2 * count + compressed_records(tails) + name_cost + addresses)
    # This bank has identical layers in every patch. Preserve that explicitly
    # with layer references above; here benchmark its simpler single-layer
    # specialization. This variant needs a fallback for future split/doubles.
    if all(layers[2*i] == layers[2*i+1] for i in range(count)):
        compact = [p[loff:loff + lsize] + p[tailoff:] for p in patches]
        for group in (1, 2, 4, 8, 16, 80):
            blocks = [b''.join(compact[i:i + group]) for i in range(0, count, group)]
            record(f'LZ4 compact records, {group} patches/block', compressed_records(blocks) + name_cost + addresses)
            for i, p in enumerate(patches):
                restored = p[:loff] + compact[i][:lsize] * 2 + compact[i][lsize:]
                assert restored == p

    # A schema-free codec: dictionary of most frequent 32-bit words. 255 escapes
    # a literal word, so every possible future Q16/enum combination is supported.
    dictionary = [v for v, _ in collections.Counter(v for p in patches for v in words(p[loff:])).most_common(255)]
    lookup = {v: i for i, v in enumerate(dictionary)}

    def encode(data):
        return b''.join(bytes([lookup[v]]) if v in lookup else b'\xff' + unwords([v]) for v in words(data))

    def decode(data):
        result, i = [], 0
        while i < len(data):
            v = data[i]
            i += 1
            if v == 255:
                result.extend(words(data[i:i + 4]))
                i += 4
            else:
                result.append(dictionary[v])
        return unwords(result)

    for data in unique + tails:
        assert decode(encode(data)) == data
    encoded = [encode(p[loff:]) for p in patches]
    record('Word dictionary + per-patch LZ4 + names', compressed_records(encoded) + 4 * len(dictionary) + name_cost + addresses)
    record('Word dictionary + unique-layer LZ4 + tail LZ4 + names', compressed_records([encode(x) for x in unique]) + compressed_records([encode(x) for x in tails]) + 4 * len(dictionary) + 2 * count + name_cost + addresses)

    # Sparse modal baseline per word position. Store a byte word position and
    # one dictionary token/literal for each differing word; offsets end records.
    def sparse(records):
        vectors = [words(r) for r in records]
        base = [collections.Counter(v).most_common(1)[0][0] for v in zip(*vectors)]
        assert len(base) <= 256
        size = 4 * len(base) + 2 * (len(records) + 1)
        for vector, original in zip(vectors, records):
            changes = [(i, v) for i, v in enumerate(vector) if v != base[i]]
            payload = b''.join(bytes([i]) + encode(unwords([v])) for i, v in changes)
            size += len(payload)
            restored = base.copy()
            cursor = 0
            while cursor < len(payload):
                position, token = payload[cursor:cursor + 2]
                cursor += 2
                if token == 255:
                    restored[position] = words(payload[cursor:cursor + 4])[0]
                    cursor += 4
                else:
                    restored[position] = dictionary[token]
            assert unwords(restored) == original
        return size

    record('Sparse modal words + dictionary + unique layers + names', sparse(unique) + sparse(tails) + 4 * len(dictionary) + 2 * count + name_cost + addresses)
    unique_tails = list(dict.fromkeys(tails))
    record('Sparse modal words + dictionary + unique layers/tails + names', sparse(unique) + sparse(unique_tails) + 4 * len(dictionary) + 3 * count + name_cost + addresses)

    # Per-column lossless palettes across unique layers and tails. Constants
    # use zero record bits. Descriptor is u16 palette offset + u8 count + u8 bits;
    # palette entries are u32. Bits are packed independently within each record.
    def palettes(records):
        vectors = [words(r) for r in records]
        tables = [list(dict.fromkeys(col)) for col in zip(*vectors)]
        bits = [(len(t) - 1).bit_length() for t in tables]
        packed_size = (sum(bits) + 7) // 8
        for vector, original in zip(vectors, records):
            packed, shift = 0, 0
            for value, table, width in zip(vector, tables, bits):
                packed |= table.index(value) << shift
                shift += width
            payload = packed.to_bytes(packed_size, 'little')
            packed = int.from_bytes(payload, 'little')
            decoded, shift = [], 0
            for table, width in zip(tables, bits):
                decoded.append(table[(packed >> shift) & ((1 << width) - 1)])
                shift += width
            assert unwords(decoded) == original
        return 4 * len(tables) + sum(4 * len(t) for t in tables) + packed_size * len(records), {
            'word_columns': len(tables), 'constant_columns': bits.count(0),
            'bits_per_record': sum(bits), 'bytes_per_record': packed_size,
            'palette_entries': sum(map(len, tables)),
        }

    lp, layer_palette = palettes(unique)
    tp, tail_palette = palettes(tails)
    record('Per-word palettes + unique layers + names', lp + tp + 2 * count + name_cost + addresses)
    stats = {
        'patches': count, 'patch_bytes': psize, 'layer_bytes': lsize,
        'tail_bytes': psize - tailoff, 'fx_bytes': fxsize,
        'names_fixed_bytes': loff * count, 'names_packed_with_offsets_bytes': name_cost,
        'upper_equals_lower': sum(layers[2*i] == layers[2*i+1] for i in range(count)),
        'unique_layers': len(unique), 'unique_tails': len(set(tails)),
        'voice_modes': dict(collections.Counter(p[tailoff] for p in patches)),
        'zero_bytes_percent': round(100 * raw.count(0) / len(raw), 2),
        'layer_palette': layer_palette, 'tail_palette': tail_palette,
        'all_roundtrips_passed': True,
    }
    (out / 'results.json').write_text(json.dumps({'stats': stats, 'encodings': rows}, indent=2) + '\n')
    print(json.dumps(stats, indent=2))
    for label, row in rows.items():
        print(f"{row['bytes']:6d} B  {row['saving_percent']:6.2f}% saved  {label}")


if __name__ == '__main__':
    main()
