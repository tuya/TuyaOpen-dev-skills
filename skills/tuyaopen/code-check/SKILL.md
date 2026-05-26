---
name: tuyaopen/code-check
description: >-
  Check C/C++ code formatting, detect Chinese characters, and validate file
  headers using clang-format and check_format.py. Use when the user mentions
  code format, lint, clang-format, style check, PR check, or after editing
  C/C++ files. 代码格式、格式检查、代码风格、PR检查、代码规范。
license: Apache-2.0
compatibility:
  - clang-format installed (Linux: `apt install clang-format`; macOS: `brew install clang-format`; Windows: `choco install llvm` or LLVM release)
  - Python 3 (venv active)
---

# TuyaOpen Code Format Check

> **SDK root:** All `$OPEN_SDK_PYTHON tools/check_format.py` commands must be run from the TuyaOpen SDK root (`$OPEN_SDK_ROOT`). The bundled `check_files.py` script resolves the SDK root automatically via `$OPEN_SDK_ROOT` or by walking upward for `.clang-format`.

## Overview

`tools/check_format.py` validates C/C++ files (`.c`, `.cpp`, `.h`, `.hpp`, `.cc`, `.cxx`) against three rules:

1. **clang-format compliance** — governed by `.clang-format` at the repo root (LLVM-based style with 4-space indent).
2. **No Chinese characters** — checks **all** content including comments and strings. Only English text is allowed in source code.
3. **Proper file headers** — Doxygen-style with `@file`, `@brief`, and `@copyright` (must include current year + "All Rights Reserved").

Paths listed in `.clang-format-ignore` are excluded (third-party libraries: cJSON, FlashDB, lwip, coreMQTT, etc.).

### Prerequisites

`clang-format` must be installed. It is included in the system dependencies (`sudo apt-get install clang-format`). If missing, the format check will be skipped with a warning.

## Usage

All commands must be run from the **SDK root** (`$OPEN_SDK_ROOT`, where `.clang-format` lives).

### Check specific files (recommended for Agent use)

```bash
$OPEN_SDK_PYTHON tools/check_format.py --debug --files path/to/file.c path/to/file.h
```

Supports glob patterns: `--files "src/tal_system/**/*.c"`

### Check a directory recursively

```bash
$OPEN_SDK_PYTHON tools/check_format.py --debug --dir src/tal_system/
```

### Check all files in current directory (debug mode fallback)

```bash
$OPEN_SDK_PYTHON tools/check_format.py --debug
```

When `--debug` is used without `--files` or `--dir`, it scans the current working directory recursively for all C/C++ files.

### PR mode (CI / pre-merge)

Checks files modified relative to a base branch (uses `git diff`):

```bash
$OPEN_SDK_PYTHON tools/check_format.py                     # default: --base master
$OPEN_SDK_PYTHON tools/check_format.py --base main          # custom base branch
```

### Verbose output

Add `-v` to any mode for detailed information:

```bash
$OPEN_SDK_PYTHON tools/check_format.py --debug --files foo.c -v
```

## Important Notes

- `--files` and `--dir` **require** `--debug` flag — they are ignored in PR mode.
- The script locates the SDK root by searching upward for `.clang-format`.
- Exit code: `0` = all checks pass, `1` = errors found.
- Header **warnings** (suggestions) do not cause failure; only **errors** do.

## Agent Workflow

When editing C/C++ files in this repo:

1. Make your changes.
2. **Check for sensitive information** before committing (see below).
3. Run the bundled wrapper: `$OPEN_SDK_PYTHON .agents/skills/tuyaopen/code-check/scripts/check_files.py <changed_files>`
   Or directly: `$OPEN_SDK_PYTHON tools/check_format.py --debug --files <changed_files>`
4. If **format errors**: run `clang-format -style=file -i <file>` to auto-fix, then re-check.
5. If **Chinese character errors**: replace Chinese text with English — this applies to comments and strings too, not just identifiers.
6. If **header errors**: ensure the file starts with a proper Doxygen header (see template below). Pay attention to the copyright year.

## Sensitive Information Check

Before committing or pushing code, verify that **no sensitive information** is included:

- **Device credentials**: `UUID`, `AuthKey`, `TUYA_OPENSDK_UUID`, `TUYA_OPENSDK_AUTHKEY` — must use placeholder values (e.g. `"your_uuid_here"`), never real credentials.
- **Product IDs**: `TUYA_PRODUCT_ID` — use a placeholder or a development-only PID.
- **API keys / tokens**: any hardcoded cloud API keys, access tokens, or passwords.
- **Private keys / certificates**: TLS private keys, certificate files, or PEM content embedded in source.
- **Network credentials**: Wi-Fi SSID/password, server URLs with credentials.

### Agent strategy

When generating or modifying code that involves `tuya_config.h` or similar credential files:

1. Always use placeholder values: `"your_uuid_here"`, `"your_authkey_here"`.
2. Warn the user if real credentials appear to be present (non-placeholder UUIDs/keys that look like actual hex or alphanumeric strings of expected length).
3. Never log, print, or include credentials in debug output, comments, or commit messages.

## File Header Template

Every `.c` and `.h` file **must** start with a `/**` comment block containing `@file`, `@brief`, `@version`, `@date`, and `@copyright`:

```c
/**
 * @file filename.c
 * @brief Brief description in English
 * @version 1.0
 * @date YYYY-MM-DD
 * @copyright Copyright (c) 2025 Tuya Inc. All Rights Reserved.
 */
```

`@copyright` format: `Copyright (c) <start_year>[-<end_year>] <holder> All Rights Reserved.` — the year must include the current year (either as start or end year). This is enforced as an **error** by `check_format.py`.

## What `.clang-format-ignore` Excludes

The following third-party paths are excluded from formatting checks:

```
src/libcjson/cJSON
src/tal_kv/FlashDB
src/tal_kv/littlefs
src/common/backoffAlgorithm
src/liblwip/lwip-2.1.2
src/libhttp/coreHTTP
src/libmqtt/coreMQTT
src/common/qrcode
```

Do not modify these third-party files for formatting. If you add new third-party code, add its path to `.clang-format-ignore`.

## Related

- The `.clang-format` config at SDK root defines the full formatting rules (LLVM-based, 4-space indent, brace after control statement, etc.)
