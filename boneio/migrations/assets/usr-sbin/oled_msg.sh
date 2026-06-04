#!/bin/bash
# oled_msg.sh — wrapper for optional Python SH1106 renderer
# Usage: oled_msg.sh "Line 1" ["Line 2"] ["Line 3"] ["Line 4"]
#        oled_msg.sh --serve    # start daemon (keeps luma in memory)
#        oled_msg.sh --stop     # stop daemon
#        oled_msg.sh clear      # clear display

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_RENDERER="${SCRIPT_DIR}/oled_msg.py"
VENV_PYTHON="/home/boneio/boneio/venv/bin/python3"
OLED_FIFO="/tmp/.oled_fifo"
OLED_PID="/tmp/.oled_serve.pid"

if [ ! -f "${PYTHON_RENDERER}" ]; then
    exit 0
fi

# Pick the right Python
PYTHON=""
if [ -x "${VENV_PYTHON}" ]; then
    PYTHON="${VENV_PYTHON}"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    exit 0
fi

# Handle --serve: start daemon in background
if [ "$1" = "--serve" ]; then
    "${PYTHON}" "${PYTHON_RENDERER}" --serve 2>/dev/null &
    # Wait briefly for FIFO to be created
    for i in $(seq 1 20); do
        [ -p "$OLED_FIFO" ] && break
        sleep 0.1
    done
    exit 0
fi

# Handle --stop: send quit command to daemon
if [ "$1" = "--stop" ]; then
    if [ -p "$OLED_FIFO" ]; then
        echo "quit" > "$OLED_FIFO" 2>/dev/null || true
    fi
    exit 0
fi

# Normal message: try FIFO (fast), fallback to direct call
if [ -p "$OLED_FIFO" ] && [ -f "$OLED_PID" ]; then
    # Daemon is running — send via FIFO (instant, no Python startup)
    MSG=$(IFS='|'; echo "$*")
    echo "$MSG" > "$OLED_FIFO" 2>/dev/null && exit 0
fi

# Fallback: direct Python call
"${PYTHON}" "${PYTHON_RENDERER}" "$@" 2>/dev/null || true
