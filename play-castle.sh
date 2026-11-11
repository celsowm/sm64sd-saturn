#!/bin/sh
set -eu
root=$(CDPATH= cd "$(dirname "$0")" && pwd)
source=${LIBSATURN_SOURCE:-$root/../lib-saturn}
bios=${LIBSATURN_BIOS:-$source/bios/firmware/mpr-17933.bin}
cue=$root/build/castle/disc/sm64ds_castle.cue
if [ ! -f "$cue" ]; then "$root/build-castle.sh"; fi
exec "$source/emulators/mednafen/run-mednafen.sh" "$cue" --bios "$bios" -- "$@"
