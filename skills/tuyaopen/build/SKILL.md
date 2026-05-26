---
name: tuyaopen/build
description: >-
  Build and compile TuyaOpen projects, select build configurations, edit
  Kconfig options, clean artifacts, and run Linux ELF binaries. Use when the
  user mentions compiling, building, tos.py build, config choice, menuconfig,
  Kconfig, build error, or running a project.
  项目编译、构建、编译配置、清理编译、编译错误、menuconfig、Kconfig。
license: Apache-2.0
compatibility:
  - TuyaOpen environment activated (export.sh / export.ps1 / export.bat)
  - cmake >= 3.28, ninja >= 1.6
---

# TuyaOpen Build

Docs: <https://tuyaopen.ai/docs/quick-start/project-compilation>

> **SDK root:** All paths and commands in this skill are relative to the TuyaOpen SDK root (`$OPEN_SDK_ROOT` on Linux/macOS/PowerShell, `%OPEN_SDK_ROOT%` on Windows CMD). Activate the environment first — see skill `tuyaopen/env-setup`.

## Project Locations

Buildable projects live in two directories:

- `apps/` — application projects (e.g. `apps/tuya_cloud/switch_demo`, `apps/tuya.ai/your_chat_bot`)
- `examples/` — example projects (e.g. `examples/get-started/sample_project`, `examples/peripherals/gpio`)

Navigate into the target project before building:

```bash
cd apps/tuya_cloud/switch_demo
```

## Configuration

### Selecting a Verified Config

```bash
tos.py config choice                           # interactive — list and pick
tos.py config choice -c TUYA_T5AI_EVB         # non-interactive — select by name (Agent / CI)
tos.py config choice -d                        # interactive — board default configs only
tos.py config choice -d -c TUYA_T5AI_EVB      # non-interactive — from board defaults
```

All variants trigger a full clean. The selected config is written to `app_default.config`.

Config lookup priority: project `config/` dir > `boards/` global configs.

**`-c` flag (non-interactive, preferred for Agent / CI):**  
Matches config by filename — `.config` extension is optional (`TUYA_T5AI_EVB` and `TUYA_T5AI_EVB.config` are equivalent).  
If the name is not found, the command exits with an error and prints the available config names.

### Fine-Tuning with Menuconfig (requires TTY)

```bash
tos.py config menu    # terminal-based Kconfig editor; resolves depends on/select automatically
tos.py config save    # interactive (requires TTY) — save current config as named preset
```

Menuconfig keys: arrows or `h`/`j`/`k`/`l`; `?` for help; write to `app_default.config` on exit.

### Writing a Custom Config (Agent / CI)

Edit `app_default.config` in the project directory. The file uses **Kconfig defconfig format** — only specify values that **differ from defaults**:

```
CONFIG_PROJECT_VERSION="1.0.1"
CONFIG_BOARD_CHOICE_T5AI=y
CONFIG_BOARD_CHOICE_TUYA_T5AI_CORE=y
CONFIG_ENABLE_LIBLVGL=y
CONFIG_ENABLE_MBEDTLS_SSL_MAX_CONTENT_LEN=4096
# CONFIG_ENABLE_COMP_AI_DISPLAY is not set
```

Key points:
- `CONFIG_BOARD_CHOICE_<PLATFORM>=y` selects the platform (e.g. `T5AI`, `ESP32`, `LINUX`).
- `CONFIG_BOARD_CHOICE_<BOARD>=y` selects the specific board under that platform (e.g. `TUYA_T5AI_CORE`, `DNESP32S3`, `UBUNTU`). **Both platform and board are required.**
- `CHIP_CHOICE` and `PLATFORM_CHOICE` are auto-set by the board's Kconfig — do not set them manually.
- Boolean options: `CONFIG_X=y` to enable, `# CONFIG_X is not set` to disable.
- String options: `CONFIG_X="value"`. Integer options: `CONFIG_X=1234`.

Common platform + board config pairs:

| Target | `app_default.config` lines |
|--------|---------------------------|
| LINUX / Ubuntu (native x86/x64) | `CONFIG_BOARD_CHOICE_LINUX=y`<br>`CONFIG_BOARD_CHOICE_UBUNTU=y` |
| LINUX / Raspberry Pi | `CONFIG_BOARD_CHOICE_LINUX=y`<br>`CONFIG_BOARD_CHOICE_RASPBERRY_PI=y` |
| T5AI EVB | `CONFIG_BOARD_CHOICE_T5AI=y`<br>`CONFIG_BOARD_CHOICE_TUYA_T5AI_EVB=y` |
| T5AI Core | `CONFIG_BOARD_CHOICE_T5AI=y`<br>`CONFIG_BOARD_CHOICE_TUYA_T5AI_CORE=y` |
| ESP32-S3 | `CONFIG_BOARD_CHOICE_ESP32=y`<br>`CONFIG_BOARD_CHOICE_ESP32_S3=y` |

### Config Pipeline

Understanding how config flows into the build (all paths relative to the project directory):

```
app_default.config          (your edits — defconfig format)
    ↓ tos.py build
.build/cache/using.config   (fully expanded .config with all defaults resolved)
    ↓ conf2cmake.py
.build/cache/using.cmake    (CMake variables: set(CONFIG_X "y"))
    ↓ conf2h.py
.build/cache/include/tuya_kconfig.h  (C macros: #define CONFIG_X 1)
```

If a build fails due to config issues, check `.build/cache/using.config` to see the **fully resolved** config (with all defaults filled in).

## Kconfig Dependency Guide

Detailed `select` / `depends on` / `if` mechanisms and agent strategy: `references/KCONFIG_GUIDE.md`.

## Build

```bash
tos.py build        # standard build
tos.py build -v     # verbose (shows full compiler commands)
```

> **Agent / CI:** Before the first build in a non-interactive session, prevent platform-update prompts:
> ```bash
> mkdir -p .cache && touch .cache/.dont_prompt_update_platform
> ```
> Create this file once after activating the environment. Without it, `tos.py build` may hang waiting for a `y/n/d` prompt when the platform commit has changed.

### Build All Configs (testing)

```bash
tos.py dev bac      # build-all-configs: for each config in the project, full-clean then build
```

Each config triggers a full clean before building, so this can take a long time. Useful for verifying all board variants compile cleanly.

## Clean

```bash
tos.py clean        # ninja clean
tos.py clean -f     # full clean — deletes .build/ entirely
```

`config choice` and `config menu` also trigger a full clean automatically.

## Running (LINUX target)

> Paths below are relative to the **project directory** (where you ran `tos.py build`), not the SDK root.

LINUX platform produces a native ELF binary. Build output is copied to `dist/`:

```bash
./dist/<project_name>_<version>/<project_name>_<version>.elf
```

A copy also exists at `.build/bin/` during the build. The `dist/` path is the canonical output location printed at the end of a successful build.

Example (for a project named `hello_world_linux` version 1.0.0):

```bash
./dist/hello_world_linux_1.0.0/hello_world_linux_1.0.0.elf
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Slow build on Windows | `MSPCManagerService` interference | Kill the process; add project dir to Windows Security exclusions |
| Toolchain download fails | Network issue | Retry `tos.py build`; check `platform/` directory |
| Build fails after config change | Incompatible options | `tos.py clean -f` then re-select: `tos.py config choice -c <name>` (non-interactive) or `tos.py config choice` (interactive) |
| `No rule to make target` | Stale build cache | `tos.py clean -f && tos.py build` |
| Build hangs with `y/n/d` prompt (Agent/CI) | Platform commit mismatch, missing suppress file | Run `mkdir -p .cache && touch .cache/.dont_prompt_update_platform` before building, or `tos.py update` first |
| Config option silently ignored | Missing `depends on` prerequisite | Check `.build/cache/using.config` to verify; grep Kconfig files for dependency chain |
| `FATAL_ERROR ... using.config` | No config selected yet | Run `tos.py config choice -c <name>` (non-interactive) or `tos.py config choice` (interactive) |
| Build succeeds but ELF not in `dist/` | Platform linker did not produce expected binary name | Check `.build/bin/` for the raw output; verify project name matches directory name |
