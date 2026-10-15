#!/bin/bash
set -euo pipefail

rom="$1/cutscene/build/rom"
share="$(pkg-config --variable=prefix ngdevkit)/share/ngdevkit"
empty="$(mktemp)"
z80-neogeo-ihx-sdobjcopy -I ihex -O binary \
    "$share/nullsound_driver.ihx" "$empty" --pad-to 131072
test "$(wc -c < "$rom/ngdevkit-m1.m1")" -eq 131072
if cmp -s "$rom/ngdevkit-m1.m1" "$empty"; then
    echo "the cartridge has the empty driver, not the movie's" >&2
    exit 1
fi
echo "the movie's own sound driver built from the bundle"
