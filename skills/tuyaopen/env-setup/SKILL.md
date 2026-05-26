---
name: tuyaopen/env-setup
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

Docs: <https://tuyaopen.ai/docs/quick-start/enviroment-setup>

## Step 0: Check if already activated (do this first)

| Variable | Set by activation | Meaning |
|----------|------------------|---------|
| `$OPEN_SDK_ROOT` | yes | SDK root path |
| `$OPEN_SDK_PYTHON` | yes | venv Python executable |
| `$VIRTUAL_ENV` | yes | active venv path |

**Linux / macOS:**
```bash
if [ -n "$OPEN_SDK_ROOT" ] && [ -n "$VIRTUAL_ENV" ]; then
    echo "Already activated"
else
    cd "$(git rev-parse --show-toplevel)" && . ./export.sh
fi
```

**Windows PowerShell:**
```powershell
if ($env:OPEN_SDK_ROOT -and $env:VIRTUAL_ENV) {
    Write-Host "Already activated"
} else {
    Set-Location (git rev-parse --show-toplevel); . .\export.ps1
}
```

**Windows CMD:**
```batch
if defined OPEN_SDK_ROOT if defined VIRTUAL_ENV (echo Already activated) else (
    for /f "delims=" %%i in ('git rev-parse --show-toplevel') do cd /d "%%i"
    call export.bat
)
```

## Step 1: Install system dependencies

**Ubuntu / Debian:**
```bash
sudo apt-get install lcov cmake-curses-gui build-essential ninja-build \
    wget git python3 python3-pip python3-venv libc6-i386 libsystemd-dev
```

macOS / Windows: see official docs linked above.

## Step 2: Activate

Run once per terminal session from the SDK root:

```bash
. ./export.sh      # Linux / macOS
.\export.ps1       # Windows PowerShell
export.bat         # Windows CMD
```

After activation: `$OPEN_SDK_ROOT`, `$OPEN_SDK_PYTHON`, `$OPEN_SDK_PIP` are set; SDK root is in `PATH`.

## Step 3: Verify

```bash
tos.py version    # e.g. v1.3.0-23-g6bcb5aa
tos.py check      # validates tool versions + runs git submodule update --init
```

Or run the bundled check script:

| Platform | Command |
|----------|---------|
| Linux / macOS | `.agents/skills/tuyaopen/env-setup/scripts/check_env.sh` |
| Windows CMD | `.agents\skills\tuyaopen\env-setup\scripts\check_env.bat` |
| Windows PowerShell | `.agents/skills/tuyaopen/env-setup/scripts/check_env.ps1` |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `python3-venv` missing | `sudo apt-get install python3-venv` |
| Activation fails, `.venv/` exists | `rm -rf .venv/ && . ./export.sh` |
| `tos.py: command not found` | Re-run `. ./export.sh` |
| Submodule download fails | `git submodule update --init` |
| `[Unknown version]` | No git tags — harmless |
