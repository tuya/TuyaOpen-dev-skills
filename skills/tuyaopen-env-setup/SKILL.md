---
name: tuyaopen-env-setup
description: >-
  Set up and activate the TuyaOpen development environment, install system
  dependencies, and initialize tos.py. Use when the user mentions environment
  setup, activating the SDK, installing dependencies, export.sh, or when
  tos.py is not found. 环境搭建、环境初始化、激活开发环境、安装依赖。
license: Apache-2.0
compatibility:
  - Ubuntu/Debian with apt-get (or macOS/Windows equivalent)
  - Python >= 3.6
  - git >= 2.0, cmake >= 3.28, make >= 3.0, ninja >= 1.6
---

# TuyaOpen Environment Setup

Docs: <https://tuyaopen.io/docs/quick-start/enviroment-setup>

## System Dependencies (Ubuntu / Debian)

```bash
sudo apt-get install lcov cmake-curses-gui build-essential ninja-build \
    wget git python3 python3-pip python3-venv libc6-i386 libsystemd-dev
```

For Mac or Windows, refer to the official docs linked above.

## Activation

The environment **must be activated once per terminal session** from the repo root:

```bash
cd <repo_root>
. ./export.sh
```

### What `export.sh` does

1. Checks if `$VIRTUAL_ENV` already points to `$OPEN_SDK_ROOT/.venv` — if so, returns immediately (idempotent).
2. Locates the repo root by looking for `export.sh` + `requirements.txt` next to each other.
3. Validates Python >= 3.6 (`python3` preferred, falls back to `python`).
4. Creates `.venv/` if missing, activates it.
5. Exports: `OPEN_SDK_ROOT`, `OPEN_SDK_PYTHON`, `OPEN_SDK_PIP`, adds repo root to `PATH`.
6. Runs `pip install -r requirements.txt`.
7. Clears `.cache/` temporary files.
8. Sets up bash completion for `tos.py`.

### Agent Quick-Check (skip if already active)

`$VIRTUAL_ENV` is set by venv activation; `$OPEN_SDK_ROOT` only exists after
`export.sh` has run. To avoid redundant activation:

```bash
if [ -n "$VIRTUAL_ENV" ] && echo "$VIRTUAL_ENV" | grep -q '\.venv$'; then
    echo "Already activated"
else
    cd "$(git rev-parse --show-toplevel)" && . ./export.sh
fi
```

## Quick Check (Agent)

Run the bundled verification script to check if the environment is ready:

```bash
.agents/skills/tuyaopen-env-setup/scripts/check_env.sh
```

This checks venv activation, `OPEN_SDK_ROOT`, `tos.py`, git, cmake, and python3 in one pass.

## Verification

```bash
tos.py version    # prints tag-commit, e.g. v1.3.0-23-g6bcb5aa
tos.py check      # validates tools + downloads submodules
```

`tos.py check` verifies minimum versions:

| Tool   | Min version |
|--------|-------------|
| git    | >= 2.0.0    |
| cmake  | >= 3.28.0   |
| make   | >= 3.0.0    |
| ninja  | >= 1.6.0    |

It then runs `git submodule update --init`.

## Deactivation

```bash
deactivate    # standard venv deactivate
# or
exit          # custom override that also unsets OPEN_SDK_* vars
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Activation fails | `python3-venv` not installed | `sudo apt-get install python3-venv` |
| Activation fails (venv exists) | Corrupted `.venv/` | `rm -rf .venv/ && . ./export.sh` |
| `tos.py: command not found` | Environment not activated | Run `. ./export.sh` again |
| Submodule download fails | Network issue | `git submodule update --init` manually |
| `[Unknown version]` | No git tags (forked repo) | Harmless — ignore |
