#!/usr/bin/env bash
# Wrapper around check_format.py for Agent use.
# Usage: check_files.sh <file1> [file2 ...]
# Runs from repo root, outputs structured pass/fail result.

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 <file1> [file2 ...]"
    echo "Example: $0 src/my_module/my_module.c include/my_module.h"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

find_repo_root() {
    local dir="${OPEN_SDK_ROOT:-}"
    if [ -n "$dir" ] && [ -f "$dir/.clang-format" ]; then
        echo "$dir"
        return
    fi
    dir="$(pwd)"
    while [ "$dir" != "/" ]; do
        if [ -f "$dir/.clang-format" ]; then
            echo "$dir"
            return
        fi
        dir="$(dirname "$dir")"
    done
    echo ""
}

REPO_ROOT="$(find_repo_root)"
if [ -z "$REPO_ROOT" ]; then
    echo "[ERROR] Cannot locate repo root (.clang-format not found)."
    echo "        Make sure you are inside the TuyaOpen repository."
    exit 1
fi

CHECK_SCRIPT="$REPO_ROOT/tools/check_format.py"
if [ ! -f "$CHECK_SCRIPT" ]; then
    echo "[ERROR] check_format.py not found at $CHECK_SCRIPT"
    exit 1
fi

echo "=== Code Format Check ==="
echo "Repo root: $REPO_ROOT"
echo "Files: $*"
echo ""

cd "$REPO_ROOT"

if python "$CHECK_SCRIPT" --debug --files "$@"; then
    echo ""
    echo "RESULT: All checks PASSED."
    exit 0
else
    echo ""
    echo "RESULT: Some checks FAILED."
    echo "  - Format errors: run 'clang-format -style=file -i <file>' to auto-fix"
    echo "  - Chinese chars: replace with English text"
    echo "  - Header errors: add proper Doxygen header (see skill tuyaopen-code-check)"
    exit 1
fi
