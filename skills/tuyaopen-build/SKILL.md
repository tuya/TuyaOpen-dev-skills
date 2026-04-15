---
name: tuyaopen-build
description: >-
  Build and compile TuyaOpen projects, select build configurations, edit
  Kconfig options, clean artifacts, and run Linux ELF binaries. Use when the
  user mentions compiling, building, tos.py build, config choice, menuconfig,
  Kconfig, build error, or running a project.
  项目编译、构建、编译配置、清理编译、编译错误、menuconfig、Kconfig。
license: Apache-2.0
compatibility:
  - TuyaOpen environment activated (export.sh)
  - cmake >= 3.28, ninja >= 1.6
---

# TuyaOpen Build

Docs: <https://tuyaopen.io/docs/quick-start/project-compilation>

## Prerequisites

Environment activated (`. ./export.sh`). See skill `tuyaopen-env-setup`.

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
tos.py config choice
```

Lists pre-verified configs for the current project. Triggers a full clean. Selected config is written to `app_default.config`.

Config lookup priority: project `config/` dir > `boards/` global configs.

### Fine-Tuning with Menuconfig (requires TTY)

```bash
tos.py config menu
```

Opens a terminal-based Kconfig editor. **Recommended when modifying options with complex dependencies** — it automatically resolves `depends on` / `select` relationships and prevents invalid combinations.

- Navigate: arrow keys or `h`/`j`/`k`/`l` (Windows terminal compat)
- View option details: press `?` on any item to see its help text, dependencies, and which symbols it selects
- Save and exit: the result is written to `app_default.config`

After customizing, save as a named preset for reuse:

```bash
tos.py config save    # prompts for a name, saves to project config/ dir
```

### Non-Interactive Editing (Agent / CI)

Edit `app_default.config` directly. The file uses **Kconfig defconfig format** — you only need to specify values that **differ from defaults**:

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

Understanding how config flows into the build:

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

For detailed Kconfig dependency mechanisms (`select` / `depends on` / `if`), real-world examples (LVGL + touchscreen), board `select` patterns, dependency lookup methods, and agent strategy for config changes, see `references/KCONFIG_GUIDE.md`.

## Build

```bash
tos.py build        # standard build
tos.py build -v     # verbose (shows full compiler commands)
```

For details on the internal build pipeline and system architecture, see `references/KCONFIG_GUIDE.md`.

### Build All Configs (testing)

```bash
tos.py dev bac      # build-all-configs: builds every config in the project
```

## Clean

```bash
tos.py clean        # ninja clean
tos.py clean -f     # full clean — deletes .build/ entirely
```

`config choice` and `config menu` also trigger a full clean automatically.

## Running (LINUX target)

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
| Build fails after config change | Incompatible options | `tos.py clean -f` then re-select config with `tos.py config choice` |
| `No rule to make target` | Stale build cache | `tos.py clean -f && tos.py build` |
| Build hangs with `y/n/d` prompt (Agent/CI) | Platform commit mismatch | `mkdir -p .cache && touch .cache/.dont_prompt_update_platform` after `. ./export.sh`, or `tos.py update` first. **Always create this file in non-interactive workflows.** |
| Config option silently ignored | Missing `depends on` prerequisite | Check `.build/cache/using.config` to verify; grep Kconfig files for dependency chain |
| `FATAL_ERROR ... using.config` | No config selected yet | Run `tos.py config choice` to select a config first |
| Build succeeds but ELF not in `dist/` | Platform linker did not produce expected binary name | Check `.build/bin/` for the raw output; verify project name matches directory name |
