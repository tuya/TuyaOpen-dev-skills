#!/usr/bin/env python3
"""Cross-platform wrapper around check_format.py for agent use.
Replaces check_files.sh.

Usage: python check_files.py <file1> [file2 ...]
"""
import os
import sys
import subprocess


def find_repo_root():
    """Locate repo root by searching upward for .clang-format."""
    root = os.environ.get("OPEN_SDK_ROOT", "")
    if root and os.path.isfile(os.path.join(root, ".clang-format")):
        return root
    d = os.getcwd()
    while True:
        if os.path.isfile(os.path.join(d, ".clang-format")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return ""


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_files.py <file1> [file2 ...]")
        print("Example: python check_files.py src/my_module/my_module.c")
        sys.exit(1)

    files = sys.argv[1:]
    repo_root = find_repo_root()
    if not repo_root:
        print("[ERROR] Cannot locate repo root (.clang-format not found).")
        print("        Make sure you are inside the TuyaOpen repository.")
        sys.exit(1)

    check_script = os.path.join(repo_root, "tools", "check_format.py")
    if not os.path.isfile(check_script):
        print(f"[ERROR] check_format.py not found at {check_script}")
        sys.exit(1)

    repo_abs = os.path.realpath(repo_root)
    for f in files:
        if os.path.isabs(f):
            candidate = os.path.realpath(f)
        else:
            candidate = os.path.realpath(os.path.join(repo_abs, f))
        if not (candidate == repo_abs or candidate.startswith(repo_abs + os.sep)):
            print(f"[ERROR] File path outside repo root: {f}")
            sys.exit(1)

    python = os.environ.get("OPEN_SDK_PYTHON", sys.executable)

    print("=== Code Format Check ===")
    print(f"Repo root: {repo_root}")
    print(f"Files: {' '.join(files)}")
    print()

    old_cwd = os.getcwd()
    os.chdir(repo_root)
    try:
        ret = subprocess.run(
            [python, check_script, "--debug", "--files"] + files,
            check=False,
        )
    finally:
        os.chdir(old_cwd)

    if ret.returncode == 0:
        print("\nRESULT: All checks PASSED.")
    else:
        print("\nRESULT: Some checks FAILED.")
        print("  - Format errors: run 'clang-format -style=file -i <file>' to auto-fix")
        print("  - Chinese chars: replace with English text")
        print("  - Header errors: add proper Doxygen header (see skill tuyaopen/code-check)")
        sys.exit(1)


if __name__ == "__main__":
    main()
