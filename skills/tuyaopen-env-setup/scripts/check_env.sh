#!/usr/bin/env bash
# Quick TuyaOpen environment verification.
# Returns 0 if environment is active and healthy, non-zero otherwise.

set -euo pipefail

OK=0
WARN=0

check() {
    local label="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        echo "[OK]   $label"
    else
        echo "[FAIL] $label"
        OK=1
    fi
}

warn() {
    local label="$1"
    echo "[WARN] $label"
    WARN=1
}

echo "=== TuyaOpen Environment Check ==="

if [ -n "${VIRTUAL_ENV:-}" ] && echo "$VIRTUAL_ENV" | grep -q '\.venv$'; then
    echo "[OK]   Python venv activated ($VIRTUAL_ENV)"
else
    echo "[FAIL] Python venv not activated (run: . ./export.sh)"
    OK=1
fi

if [ -n "${OPEN_SDK_ROOT:-}" ]; then
    echo "[OK]   OPEN_SDK_ROOT=$OPEN_SDK_ROOT"
else
    echo "[FAIL] OPEN_SDK_ROOT not set (run: . ./export.sh)"
    OK=1
fi

check "tos.py reachable" command -v tos.py
check "git available" git --version
check "cmake available" cmake --version
check "python3 available" python3 --version

if command -v tos.py > /dev/null 2>&1; then
    echo ""
    echo "--- tos.py version ---"
    tos.py version 2>&1 || true
fi

echo ""
if [ "$OK" -ne 0 ]; then
    echo "RESULT: Some checks FAILED. Run '. ./export.sh' from the repo root."
    exit 1
elif [ "$WARN" -ne 0 ]; then
    echo "RESULT: All checks passed with warnings."
    exit 0
else
    echo "RESULT: All checks passed."
    exit 0
fi
