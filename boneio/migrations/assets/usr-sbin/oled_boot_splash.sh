#!/bin/bash
# oled_boot_splash.sh — fast OLED boot splash wrapper
# Uses smbus2-based renderer (no luma/PIL) for instant display.
# Usage: oled_boot_splash.sh "Line 1" ["Line 2"] ["Line 3"] ["Line 4"]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_RENDERER="${SCRIPT_DIR}/oled_boot_splash.py"
VENV_PYTHON="/home/boneio/boneio/venv/bin/python3"

if [ ! -f "${PYTHON_RENDERER}" ]; then
    exit 0
fi

if [ -x "${VENV_PYTHON}" ]; then
    "${VENV_PYTHON}" "${PYTHON_RENDERER}" "$@" 2>/dev/null || true
elif command -v python3 >/dev/null 2>&1; then
    python3 "${PYTHON_RENDERER}" "$@" 2>/dev/null || true
fi
