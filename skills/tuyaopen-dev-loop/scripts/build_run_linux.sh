#!/usr/bin/env bash
# Build and run a TuyaOpen project on LINUX platform.
# Usage: build_run_linux.sh [timeout_seconds]
# Default timeout: 30 seconds. Set to 0 for no timeout.

set -euo pipefail

TIMEOUT="${1:-30}"

echo "=== TuyaOpen LINUX Build & Run ==="

if [ -z "${OPEN_SDK_ROOT:-}" ]; then
    echo "[ERROR] Environment not activated. Run '. ./export.sh' first."
    exit 1
fi

if [ ! -f "app_default.config" ]; then
    echo "[ERROR] No app_default.config found. Run 'tos.py config choice' first."
    exit 1
fi

echo "--- Building ---"
if ! tos.py build; then
    echo ""
    echo "RESULT: Build FAILED."
    exit 1
fi

BINARY=$(find .build/bin/ -maxdepth 1 -type f -executable 2>/dev/null | head -1)
if [ -z "$BINARY" ]; then
    echo "[ERROR] No executable found in .build/bin/"
    exit 1
fi

echo ""
echo "--- Running: $BINARY (timeout: ${TIMEOUT}s) ---"
echo ""

LOG_FILE="device_$(date +%Y%m%d_%H%M%S).log"

if [ "$TIMEOUT" -eq 0 ]; then
    "$BINARY" 2>&1 | tee "$LOG_FILE"
else
    timeout "$TIMEOUT" "$BINARY" 2>&1 | tee "$LOG_FILE" || true
fi

echo ""
echo "--- Log Analysis ---"

ERROR_COUNT=$(grep -c '\[.*ty E\]' "$LOG_FILE" 2>/dev/null || echo "0")
WARN_COUNT=$(grep -c '\[.*ty W\]' "$LOG_FILE" 2>/dev/null || echo "0")
WDT_COUNT=$(grep -c 'feed watchdog' "$LOG_FILE" 2>/dev/null || echo "0")

echo "Errors (ty E): $ERROR_COUNT"
echo "Warnings (ty W): $WARN_COUNT"
echo "Watchdog feeds: $WDT_COUNT"
echo "Log saved to: $LOG_FILE"

if [ "$ERROR_COUNT" -gt 0 ]; then
    echo ""
    echo "--- Error lines ---"
    grep '\[.*ty E\]' "$LOG_FILE" || true
    echo ""
    echo "RESULT: Runtime ERRORS detected."
    exit 1
fi

echo ""
echo "RESULT: Run completed. No errors detected."
exit 0
