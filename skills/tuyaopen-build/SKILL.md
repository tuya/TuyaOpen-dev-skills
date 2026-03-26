---
name: tuyaopen-build
description: >-
  Build and compile TuyaOpen projects, select build configurations, edit
  Kconfig options, clean artifacts, and run Linux ELF binaries. Use when the
  user mentions compiling, building, tos.py build, config choice, menuconfig,
  Kconfig, build error, or running a project.
  项目编译、构建、编译配置、清理编译、编译错误、menuconfig、Kconfig。
---

# TuyaOpen Build

Docs: <https://tuyaopen.ai/zh/docs/quick-start/project-compilation>

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
- `CONFIG_BOARD_CHOICE_<PLATFORM>=y` selects the platform (e.g. `T5AI`, `ESP32`).
- `CONFIG_BOARD_CHOICE_<BOARD>=y` selects the specific board under that platform (e.g. `TUYA_T5AI_CORE`, `DNESP32S3`). Both are needed.
- `CHIP_CHOICE` and `PLATFORM_CHOICE` are auto-set by the board's Kconfig — do not set them manually.
- Boolean options: `CONFIG_X=y` to enable, `# CONFIG_X is not set` to disable.
- String options: `CONFIG_X="value"`. Integer options: `CONFIG_X=1234`.

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

### Three dependency mechanisms

| Mechanism | Behavior | Effect on manual editing |
|-----------|----------|--------------------------|
| `select X` | When this option is enabled, `X` is **force-enabled** regardless of `X`'s own `depends on` | Safe to omit `X` from your config — it will be auto-enabled |
| `depends on X` | This option is **hidden/unavailable** unless `X` is enabled | You **must** enable `X` first, or your option will be silently ignored |
| `if (X)` block | All options inside the block require `X` to be enabled | Same as `depends on` — enable `X` first |

### Example: enabling LVGL with touchscreen

The dependency chain:

```
ENABLE_LIBLVGL (src/liblvgl/Kconfig)
  └── select ENABLE_DISPLAY      ← auto-enabled by LVGL
        └── ENABLE_TP            ← depends on ENABLE_DISPLAY (must enable manually)
              └── LVGL_ENABLE_TP ← depends on ENABLE_LIBLVGL (inside if block)
```

So in `app_default.config`, you need:
```
CONFIG_ENABLE_LIBLVGL=y       # this auto-selects ENABLE_DISPLAY
CONFIG_LVGL_ENABLE_TP=y       # this auto-selects ENABLE_TP
```

### How boards use `select`

Board Kconfig files (e.g. `boards/T5AI/TUYA_T5AI_EVB/Kconfig`) use `BOARD_CONFIG` with multiple `select` statements to auto-enable features the board supports:

```kconfig
config BOARD_CONFIG
    bool
    default y
    select ENABLE_AUDIO_CODECS
    select ENABLE_LED
    select ENABLE_BUTTON
    select ENABLE_DISPLAY
    select ENABLE_LVGL_OS_FREERTOS if (LVGL_VERSION_9)
```

This means selecting a board automatically pulls in its supported peripherals.

### Finding dependency information

When you need to understand an option's dependencies:

1. **In menuconfig**: press `?` on the option to see full details.
2. **Read Kconfig source files**:
   - Platform/board: `boards/<PLATFORM>/Kconfig`, `boards/<PLATFORM>/<BOARD>/Kconfig`
   - SDK components: `src/Kconfig` (entry point), `src/<component>/Kconfig`
   - Peripherals: `src/peripherals/<driver>/Kconfig`
   - LVGL: `src/liblvgl/Kconfig`
   - AI service: `src/tuya_ai_service/Kconfig`
3. **Search for the symbol**: `grep -r "CONFIG_ENABLE_FOO\|ENABLE_FOO" boards/ src/ --include="Kconfig*"`

### Agent strategy for config changes

1. **Simple changes** (toggling a well-known boolean): edit `app_default.config` directly.
2. **Options with `depends on`**: grep the relevant Kconfig files first to find the full dependency chain, then add all required options.
3. **Complex or unfamiliar changes**: if TTY is available, use `tos.py config menu` which handles dependencies automatically. If not, start from a known-good config file in the project's `config/` directory and modify incrementally.
4. **After manual edits**: run `tos.py build` — if a required dependency is missing, the build system will either error out or silently disable the option. Check `.build/cache/using.config` to verify your options were actually applied.

## Build

```bash
tos.py build        # standard build
tos.py build -v     # verbose (shows full compiler commands)
```

### What happens internally

1. Downloads the platform toolchain to `platform/<PLATFORM>/` (first time only).
2. Runs toolchain `prepare` step.
3. Processes `app_default.config` through Kconfiglib to generate `using.config`, `using.cmake`, and `tuya_kconfig.h`.
4. CMake generates build files in `.build/` using `ninja`.
5. Root `CMakeLists.txt` scans `src/` via `list_components()` — every subdirectory with its own `CMakeLists.txt` becomes an SDK component automatically.
6. Board-level code from `boards/<PLATFORM>/<BOARD>/CMakeLists.txt` is included.
7. Application code from the project's `CMakeLists.txt` is built as `tuyaapp` and linked against the `tuyaos` static library.
8. Final binaries go to `.build/bin/`.

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

LINUX platform produces a native ELF binary:

```bash
./.build/bin/<project_name>_<version>
```

The exact filename is printed at the end of a successful build.

## Build System Architecture

```
app_default.config (defconfig)
    │
    ▼  Kconfiglib
.build/cache/
├── using.config        → fully resolved config
├── using.cmake         → CMake variables (included by root CMakeLists.txt)
└── include/tuya_kconfig.h → C preprocessor macros

Root CMakeLists.txt
├── tools/kconfiglib/           → config processing
├── platform/<PLATFORM>/        → toolchain_file.cmake, platform_config.cmake
├── src/<component>/            → auto-discovered by list_components()
│   ├── tal_system, tal_wifi, tal_security, ...
│   ├── liblwip, libtls, libcjson, liblvgl, ...
│   └── peripherals/button, peripherals/display, ...
├── boards/<PLATFORM>/<BOARD>/  → board-specific drivers and Kconfig
└── <project>/CMakeLists.txt    → application code (tuyaapp library)
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Slow build on Windows | `MSPCManagerService` interference | Kill the process; add project dir to Windows Security exclusions |
| Toolchain download fails | Network issue | Retry `tos.py build`; check `platform/` directory |
| Build fails after config change | Incompatible options | `tos.py clean -f` then re-select config with `tos.py config choice` |
| `No rule to make target` | Stale build cache | `tos.py clean -f && tos.py build` |
| Build hangs with `y/n/d` prompt (Agent/CI) | Platform commit mismatch | `mkdir -p .cache && touch .cache/.dont_prompt_update_platform` after `. ./export.sh`, or `tos.py update` first |
| Config option silently ignored | Missing `depends on` prerequisite | Check `.build/cache/using.config` to verify; grep Kconfig files for dependency chain |
| `FATAL_ERROR ... using.config` | No config selected yet | Run `tos.py config choice` to select a config first |
