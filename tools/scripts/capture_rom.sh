#!/usr/bin/env bash
set -euo pipefail

FRAMES="${1:-600}"
OUT="${2:-build/last-capture.png}"
ROM="${ROM:-build/neogeomedia.neo}"
CORE="${CORE:-$HOME/Library/Application Support/RetroArch/cores/geolith_libretro.dylib}"
OPTS="${OPTS:-$HOME/Library/Application Support/RetroArch/config/Geolith/Geolith.opt}"
FULL_RASTER="${FULL_RASTER:-0}"

if [[ ! -f "$ROM" ]]; then
    echo "cart not found: $ROM" >&2
    exit 1
fi
if [[ ! -f "$CORE" ]]; then
    echo "geolith core not found: $CORE" >&2
    exit 1
fi

absolute() {
    case "$1" in
        /*) printf '%s\n' "$1" ;;
        *) printf '%s/%s\n' "$PWD" "$1" ;;
    esac
}

restore_opts() {
    if [[ -n "${OPTS_BACKUP:-}" && -f "$OPTS_BACKUP" ]]; then
        mv -f "$OPTS_BACKUP" "$OPTS"
    fi
}

if [[ "$FULL_RASTER" == "1" && -f "$OPTS" ]]; then
    OPTS_BACKUP="$(mktemp -t geolith-opt-XXXXXX)"
    cp "$OPTS" "$OPTS_BACKUP"
    trap restore_opts EXIT
    command sed -i '' -E 's/^geolith_overscan_[tblr] = "[0-9]+"/&/' "$OPTS"
    for side in t b l r; do
        command sed -i '' -E "s/^geolith_overscan_${side} = \"[0-9]+\"/geolith_overscan_${side} = \"0\"/" "$OPTS"
    done
fi

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"

open -W -g -j -n /Applications/RetroArch.app \
    --stdout /tmp/capture_rom.log --stderr /tmp/capture_rom.log \
    --args -L "$CORE" \
    --max-frames="$FRAMES" \
    --max-frames-ss \
    --max-frames-ss-path="$(absolute "$OUT")" \
    "$(absolute "$ROM")"

if [[ ! -s "$OUT" ]]; then
    echo "no screenshot produced; tail of log:" >&2
    tail -20 /tmp/capture_rom.log >&2
    exit 1
fi
echo "$OUT"
