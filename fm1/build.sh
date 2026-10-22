#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Build the CPU bench (fm1/bench.c) for the FM-1's pi32v2 with the JieLi toolchain:
#   fm1/build.sh [opt]   -> build/fm1/bench.bin (flat, +0x120 pad for fm1-emu --bin) and bench.dis,
#                           build/fm1/prim.bin (fm1/prim.h: the arithmetic primitives one by one),
#                           build/fm1/play.bin (fm1/play.c) when tools/song_h.py has written song_ev.h
# JIELI_TOOLCHAIN: the toolchain (default ~/.jieli/toolchain, as fm1-harbor). It is Linux x86-64:
# on macOS every step runs in a linux/amd64 Docker container (Docker must be running).
set -eu
cd "$(dirname "$0")/.."
OPT="${1:--O2}"
TC="${JIELI_TOOLCHAIN:-$HOME/.jieli/toolchain}"
[ -x "$TC/pi32v2/bin/clang" ] || { echo "build.sh: no JieLi toolchain in $TC"; exit 1; }
mkdir -p build/fm1
STEPS=$(cat <<SH
set -e
CC="/opt/jieli/pi32v2/bin/clang -target pi32v2"
CF="$OPT -ffreestanding -nostdlib -fno-builtin -Wall -Wno-unused-function"
O=build/fm1
\$CC -c fm1/crt0.S -o \$O/crt0.o
\$CC \$CF -c engine/sc_voice.c -o \$O/sc_voice.o
\$CC \$CF -c engine/sc_synth.c -o \$O/sc_synth.o
\$CC \$CF -c fm1/bench.c -o \$O/bench.o
/opt/jieli/pi32v2/bin/ld -T fm1/bench.ld -e _start \$O/crt0.o \$O/bench.o \$O/sc_synth.o \$O/sc_voice.o -o \$O/bench.elf
/opt/jieli/common/bin/objcopy -O binary -j .text \$O/bench.elf \$O/text.bin
/opt/jieli/common/bin/objcopy -O binary -j .data \$O/bench.elf \$O/data.bin
/opt/jieli/common/bin/objdump -d \$O/bench.elf > \$O/bench.dis
\$CC \$CF -c fm1/prim_fm1.c -o \$O/prim.o
/opt/jieli/pi32v2/bin/ld -T fm1/bench.ld -e _start \$O/crt0.o \$O/prim.o -o \$O/prim.elf
/opt/jieli/common/bin/objcopy -O binary -j .text \$O/prim.elf \$O/ptext.bin
/opt/jieli/common/bin/objcopy -O binary -j .data \$O/prim.elf \$O/pdata.bin
if [ -f \$O/song_ev.h ]; then
\$CC \$CF -c fm1/play.c -o \$O/play.o
/opt/jieli/pi32v2/bin/ld -T fm1/bench.ld -e _start \$O/crt0.o \$O/play.o \$O/sc_synth.o \$O/sc_voice.o -o \$O/play.elf
/opt/jieli/common/bin/objcopy -O binary -j .text \$O/play.elf \$O/pltext.bin
/opt/jieli/common/bin/objcopy -O binary -j .data \$O/play.elf \$O/pldata.bin
fi
SH
)
if [ "$(uname -s)-$(uname -m)" = "Linux-x86_64" ]; then
    mkdir -p /tmp/jieli && ln -sfn "$TC" /opt/jieli 2>/dev/null || true
    sh -c "$STEPS"
else
    docker info >/dev/null 2>&1 || { echo "build.sh: Docker is not running"; exit 1; }
    docker run --rm --platform linux/amd64 -v "$PWD:/work" -v "$TC:/opt/jieli:ro" -w /work \
        debian:bookworm-slim sh -c "$STEPS"
fi
python3 - <<'PY'
import os
for name, t, d in (("bench", "text", "data"), ("prim", "ptext", "pdata"), ("play", "pltext", "pldata")):
    if name == "play" and not os.path.exists("build/fm1/song_ev.h"):
        continue
    b = open(f"build/fm1/{t}.bin", "rb").read() + open(f"build/fm1/{d}.bin", "rb").read()
    open(f"build/fm1/{name}.bin", "wb").write(b"\0" * 0x120 + b)
    print(f"build/fm1/{name}.bin: {len(b)} bytes (+0x120 pad)")
PY
