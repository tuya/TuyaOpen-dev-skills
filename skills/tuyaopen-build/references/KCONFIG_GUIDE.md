# Kconfig Dependency Guide

## Three Dependency Mechanisms

| Mechanism | Behavior | Effect on manual editing |
|-----------|----------|--------------------------|
| `select X` | When this option is enabled, `X` is **force-enabled** regardless of `X`'s own `depends on` | Safe to omit `X` from your config — it will be auto-enabled |
| `depends on X` | This option is **hidden/unavailable** unless `X` is enabled | You **must** enable `X` first, or your option will be silently ignored |
| `if (X)` block | All options inside the block require `X` to be enabled | Same as `depends on` — enable `X` first |

## Example: Enabling LVGL with Touchscreen

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

## How Boards Use `select`

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

## Finding Dependency Information

When you need to understand an option's dependencies:

1. **In menuconfig**: press `?` on the option to see full details.
2. **Read Kconfig source files**:
   - Platform/board: `boards/<PLATFORM>/Kconfig`, `boards/<PLATFORM>/<BOARD>/Kconfig`
   - SDK components: `src/Kconfig` (entry point), `src/<component>/Kconfig`
   - Peripherals: `src/peripherals/<driver>/Kconfig`
   - LVGL: `src/liblvgl/Kconfig`
   - AI service: `src/tuya_ai_service/Kconfig`
3. **Search for the symbol**: `grep -r "CONFIG_ENABLE_FOO\|ENABLE_FOO" boards/ src/ --include="Kconfig*"`

## Agent Strategy for Config Changes

1. **Simple changes** (toggling a well-known boolean): edit `app_default.config` directly.
2. **Options with `depends on`**: grep the relevant Kconfig files first to find the full dependency chain, then add all required options.
3. **Complex or unfamiliar changes**: if TTY is available, use `tos.py config menu` which handles dependencies automatically. If not, start from a known-good config file in the project's `config/` directory and modify incrementally.
4. **After manual edits**: run `tos.py build` — if a required dependency is missing, the build system will either error out or silently disable the option. Check `.build/cache/using.config` to verify your options were actually applied.

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

## What Happens During Build

1. Downloads the platform toolchain to `platform/<PLATFORM>/` (first time only).
2. Runs toolchain `prepare` step.
3. Processes `app_default.config` through Kconfiglib to generate `using.config`, `using.cmake`, and `tuya_kconfig.h`.
4. CMake generates build files in `.build/` using `ninja`.
5. Root `CMakeLists.txt` scans `src/` via `list_components()` — every subdirectory with its own `CMakeLists.txt` becomes an SDK component automatically.
6. Board-level code from `boards/<PLATFORM>/<BOARD>/CMakeLists.txt` is included.
7. Application code from the project's `CMakeLists.txt` is built as `tuyaapp` and linked against the `tuyaos` static library.
8. Final binaries go to `.build/bin/`.
