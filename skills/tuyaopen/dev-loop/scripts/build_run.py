#!/usr/bin/env python3
"""Build and run a TuyaOpen LINUX project. Cross-platform replacement for build_run_linux.sh.

Usage: python build_run.py [timeout_seconds]
  timeout_seconds: default 30. Pass 0 for no timeout.
"""
import datetime
import glob
import os
import subprocess
import sys


def _python_exe():
    """Venv Python: $OPEN_SDK_PYTHON (set by export.sh/ps1/bat), else sys.executable."""
    return os.environ.get("OPEN_SDK_PYTHON") or sys.executable


def _tos_py():
    return os.path.join(os.environ.get("OPEN_SDK_ROOT", "."), "tos.py")


def _log_dir():
    """Write logs to <project_dir>/.target_logging/ — gitignored by SDK .gitignore."""
    log_dir = os.path.join(os.getcwd(), ".target_logging")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def find_binary():
    for pattern in ["dist/**/*.elf", ".build/bin/*"]:
        matches = [
            f for f in glob.glob(pattern, recursive=True)
            if os.path.isfile(f) and os.access(f, os.X_OK)
        ]
        if matches:
            return matches[0]
    return None


def analyze_log(lines):
    error_count = sum(1 for l in lines if "ty E]" in l)
    warn_count  = sum(1 for l in lines if "ty W]" in l)
    wdt_count   = sum(1 for l in lines if "feed watchdog" in l)
    return error_count, warn_count, wdt_count


def main():
    timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    print("=== TuyaOpen LINUX Build & Run ===")

    if not os.environ.get("OPEN_SDK_ROOT"):
        print("[ERROR] Environment not activated. Source export.sh / export.bat / export.ps1 first.")
        sys.exit(1)

    if not os.path.isfile("app_default.config"):
        print("[ERROR] No app_default.config found. Run 'tos.py config choice' first.")
        sys.exit(1)

    print("--- Building ---")
    ret = subprocess.run([_python_exe(), _tos_py(), "build"], check=False)
    if ret.returncode != 0:
        print("\nRESULT: Build FAILED.")
        sys.exit(1)

    binary = find_binary()
    if not binary:
        print("[ERROR] No executable found in dist/ or .build/bin/")
        sys.exit(1)

    log_file = os.path.join(_log_dir(), f"device_{datetime.datetime.now():%Y%m%d_%H%M%S}.log")
    print(f"\n--- Running: {binary} (timeout: {timeout}s) ---\n")

    output_lines = []
    try:
        with open(log_file, "w") as lf:
            proc = subprocess.Popen(
                [binary],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                out, _ = proc.communicate(timeout=timeout if timeout else None)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, _ = proc.communicate()
            print(out, end="")
            lf.write(out)
            output_lines = out.splitlines(keepends=True)
    except Exception as e:
        print(f"[ERROR] Failed to run binary: {e}")
        sys.exit(1)

    print("\n--- Log Analysis ---")
    error_count, warn_count, wdt_count = analyze_log(output_lines)
    print(f"Errors (ty E): {error_count}")
    print(f"Warnings (ty W): {warn_count}")
    print(f"Watchdog feeds: {wdt_count}")
    print(f"Log saved to: {log_file}")

    if error_count > 0:
        print("\n--- Error lines ---")
        for l in output_lines:
            if "ty E]" in l:
                print(l, end="")
        print("\nRESULT: Runtime ERRORS detected.")
        sys.exit(1)

    print("\nRESULT: Run completed. No errors detected.")


if __name__ == "__main__":
    main()
