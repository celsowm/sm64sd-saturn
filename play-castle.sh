#!/bin/sh
set -eu
root=$(CDPATH= cd "$(dirname "$0")" && pwd)
source=${LIBSATURN_SOURCE:-$root/../lib-saturn}
bios=${LIBSATURN_BIOS:-$source/bios/firmware/mpr-17933.bin}
cue=$root/build/castle/disc/sm64ds_castle.cue
if [ ! -f "$cue" ]; then "$root/build-castle.sh"; fi
# The controls are permanent (see CLAUDE.md): arrows = D-pad, Q/W/E = X/Y/Z,
# A/S/D = A/B/C, R/T = L/R, Return = Start. The launcher points Mednafen at
# its own config directory, so pass every binding from the ovcfg on the
# command line: no mednafen.cfg anywhere can override them.
user_args=$#
while IFS= read -r line; do
    case "$line" in
        ss.input.*)
            set -- "$@" "-${line%% *}" "$(printf '%s' "${line#* }" | sed 's/^ *//')" ;;
    esac
done < "$root/mednafen_saturn_friendly.ovcfg"
# Rotate the caller's own options behind the bindings so they still win.
i=0
while [ "$i" -lt "$user_args" ]; do set -- "$@" "$1"; shift; i=$((i+1)); done
exec "$source/emulators/mednafen/run-mednafen.sh" "$cue" --bios "$bios" -- "$@"
