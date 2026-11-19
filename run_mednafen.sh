#!/bin/sh
# Run the built Saturn disc image in Mednafen with friendly keys.
#
# Usage: ./run_mednafen.sh [demo|keys-only]
#   demo      : launch mednafen, then inject a demo key sequence (default)
#   keys-only : just launch mednafen (you control manually)
#
# One-time macOS setup (needed for script key injection):
#   System Settings > Privacy & Security > Accessibility
#   Add Terminal (or your shell) and enable it, then re-run.
#
# Important: click Mednafen's window to focus it before keys will register.
#
# Friendly Saturn key map (mednafen_saturn_friendly.ovcfg):
#   Arrows  = D-pad (move Mario / look around)
#   Z       = A (jump)
#   X       = B (run)
#   ,       = L shoulder (camera left)
#   .       = R shoulder (camera right)
#   Space   = X (zoom)
#   C       = C (reset)
#   Return  = Start (pause)

set -eu

ROOT=$(CDPATH= cd "$(dirname "$0")" && pwd)
CUE="$ROOT/build/castle/disc/sm64ds_castle.cue"
OVCFG="$ROOT/mednafen_saturn_friendly.ovcfg"

if [ ! -f "$CUE" ]; then
    echo "ERROR: disc image not found at $CUE" >&2
    echo "Build it first: ./build-castle.sh" >&2
    exit 1
fi

MODE="${1:-demo}"

send_char() {
    osascript -e "tell application \"System Events\" to keystroke \"$1\"" >/dev/null 2>&1 || true
}

hold_key_code() {
    osascript -e "tell application \"System Events\" to key down $1" >/dev/null 2>&1 || true
    sleep "${2:-0.4}"
    osascript -e "tell application \"System Events\" to key up $1" >/dev/null 2>&1 || true
}

focus_mednafen() {
    osascript -e 'tell application "Mednafen" to activate' >/dev/null 2>&1 || true
    osascript -e 'tell application "System Events" to set frontmost of process "Mednafen" to true' >/dev/null 2>&1 || true
    sleep 1
}

launch_mednafen() {
    if pgrep -x mednafen >/dev/null 2>&1; then
        echo "Mednafen already running."
        return 0
    fi
    echo "Launching Mednafen with $CUE ..."
    echo "  Friendly key overrides: $OVCFG"
    nohup mednafen -ovconfig "$OVCFG" "$CUE" >/tmp/mednafen.log 2>&1 &
    for i in $(seq 1 30); do
        if pgrep -x mednafen >/dev/null 2>&1; then
            sleep 1
            focus_mednafen
            return 0
        fi
        sleep 0.5
    done
    echo "WARNING: Mednafen did not appear. Check /tmp/mednafen.log" >&2
}

demo_sequence() {
    echo "Sending demo key sequence to Mednafen..."
    focus_mednafen

    send_char "\r"
    sleep 1.5

    hold_key_code 126 1.5   # up arrow (move forward)
    sleep 0.5

    send_char "."           # R shoulder (camera right)
    sleep 0.5

    hold_key_code 126 1.5   # up arrow
    sleep 0.5

    send_char "z"           # A (jump)
    sleep 0.5

    hold_key_code 126 1.5   # up arrow
    sleep 0.5

    send_char ","           # L shoulder (camera left)
    sleep 0.5

    hold_key_code 124 0.6   # right arrow (look right)
    hold_key_code 123 0.6   # left arrow (look left)

    echo "Demo sequence complete."
    echo "Mednafen is still running — click its window to focus, then control manually."
    echo "Keys: arrows=move, Z=jump, X=run, ,/ .=cam L/R, space=zoom, C=reset, Return=pause"
    echo "Quit Mednafen with Command-Q."
}

if [ "$MODE" = "demo" ]; then
    launch_mednafen
    demo_sequence
else
    launch_mednafen
fi