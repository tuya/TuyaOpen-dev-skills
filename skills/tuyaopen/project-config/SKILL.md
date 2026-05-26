---
name: tuyaopen/project-config
description: >-
  Create new TuyaOpen projects and platforms, manage build configurations,
  update platform dependencies, and use tos.py subcommands.
  Use when the user mentions creating a project, tos.py new, saving or
  choosing a config, tos.py update, or general tos.py usage.
  创建项目、新建工程、配置管理、保存配置、选择配置、更新依赖。
license: Apache-2.0
compatibility:
  - TuyaOpen environment activated (export.sh / export.ps1 / export.bat)
  - TTY terminal required for interactive commands (tos.py new, config choice/menu/save)
---

# TuyaOpen Project & Config Management

> **SDK root:** All paths and commands in this skill are relative to the TuyaOpen SDK root (`$OPEN_SDK_ROOT` on Linux/macOS/PowerShell, `%OPEN_SDK_ROOT%` on Windows CMD). Activate the environment first — see skill `tuyaopen/env-setup`.

Docs: <https://tuyaopen.ai/docs/tos-tools/tos-guide>

## Creating a New Project

> All `tos.py new` subcommands are **interactive** (use `input()` / menu prompts). They require a TTY and cannot be used in non-interactive Agent/CI pipelines.

### `tos.py new project` (interactive)

Creates a new application from a template **in the current working directory**.

```bash
cd apps/my_category          # navigate to where you want the project
tos.py new project               # defaults to base framework
tos.py new project --framework arduino   # Arduino-style project
```

Flow:
1. Prompts for project name (e.g. `my_app`).
2. Copies template from `tools/app_template/<framework>/` into `<cwd>/<project_name>/`.
3. Fails if the directory already exists.

**Templates:**

| Framework | Entry file | Entry point |
|-----------|-----------|-------------|
| `base` | `src/tuya_app_main.c` | `user_main()` — on Linux runs as `main()`, on MCU spawns a thread via `tuya_app_main()` |
| `arduino` | `src/tuya_app_main.cpp` | Arduino-style `setup()` / `loop()` |

Generated project structure:
```
my_app/
├── CMakeLists.txt    # collects src/, include/, links against tuyaos
└── src/
    └── tuya_app_main.c
```

**After creation — next steps:**
1. `cd my_app`
2. Select a config: `tos.py config choice` (interactive), or manually create `app_default.config` (see skill `tuyaopen/build` for Kconfig format).
3. Build: `tos.py build`

A new project has no `app_default.config` — the build system will copy an empty template on first build, but you must configure a platform/board before a meaningful build succeeds.

### `tos.py new board` (interactive)

Creates a new board BSP directory under `boards/<platform>/`.

Flow:
1. Lists available platforms (T5AI, ESP32, LINUX, etc.) — select one.
2. Prompts for new board name (e.g. `MY_CUSTOM_BOARD`).
3. Creates `boards/<platform>/<board_name>/` with template files (Kconfig, CMakeLists.txt, board_com_api.h, board source file).
4. Automatically registers the board in `boards/<platform>/Kconfig` so it appears in `config choice`.
5. For ESP32, chip name defaults to `esp32s3`; for other platforms, uses the platform name.

See skill `tuyaopen/add-board` for the full board adaptation guide.

## Configuration Management

For detailed Kconfig editing guidance (dependency mechanisms, defconfig format, config pipeline), see skill **`tuyaopen/build`**.

### `tos.py config choice` (interactive)

```bash
tos.py config choice       # list configs from project config/ or boards/
tos.py config choice -d    # only show boards/ default configs (skip project config/)
```

Selects a pre-verified config. Writes to `app_default.config`. **Triggers a full clean first.**

Config lookup priority:
1. Project's own `config/` directory (e.g. `apps/tuya.ai/your_chat_bot/config/`)
2. `boards/<platform>/config/` global configs (shown when no project configs exist, or with `-d`)

> Note: `-d` is an option of the `choice` subcommand (not the global `--debug` flag).

### `tos.py config menu` (interactive)

```bash
tos.py config menu
```

Opens a terminal-based Kconfig editor. **Triggers a full clean first.** Best for fine-tuning options with complex dependencies — the editor resolves `select` / `depends on` automatically. See skill `tuyaopen/build` for the Kconfig Dependency Guide.

### `tos.py config save` (interactive, requires TTY)

```bash
tos.py config save
```

Prompts for a name, then copies current `app_default.config` to the project's `config/` directory as a named preset. Useful after customizing with `config menu`.

### Non-Interactive Config (Agent / CI)

Prefer `tos.py config choice -c <name>` when a pre-verified config already exists:

```bash
tos.py config choice -c TUYA_T5AI_EVB     # from project config/ dir
tos.py config choice -d -c TUYA_T5AI_EVB  # from boards/ default configs
```

Or edit `app_default.config` directly for custom configurations — no TTY needed. See skill `tuyaopen/build` for format details and Kconfig dependency handling.

## Non-Interactive Project Creation (Agent / CI)

`tos.py new` is interactive and cannot be used in Agent/CI. Create the project manually by writing three files.

### Required Directory Structure

```
<project_name>/
├── CMakeLists.txt
├── app_default.config
├── include/          # optional — create if you have shared headers
└── src/
    └── tuya_app_main.c
```

The project can live under `examples/` or `apps/` — both are valid build locations.

### Step 1: CMakeLists.txt

```cmake
##
# @file CMakeLists.txt
# @brief
#/

set(APP_PATH ${CMAKE_CURRENT_LIST_DIR})

get_filename_component(APP_NAME ${APP_PATH} NAME)

aux_source_directory(${APP_PATH}/src APP_SRC)

set(APP_INC ${APP_PATH}/include)

########################################
# Target Configure
########################################
add_library(${EXAMPLE_LIB})

target_sources(${EXAMPLE_LIB}
    PRIVATE
        ${APP_SRC}
    )

target_include_directories(${EXAMPLE_LIB}
    PRIVATE
        ${APP_INC}
    )
```

This is the standard template from `tools/app_template/base/CMakeLists.txt`. It auto-collects all `.c` files under `src/` — no need to list them individually.

### Step 2: app_default.config

Select the target platform and board. **Both a platform choice and a board choice are required.**

Common platform + board pairs:

| Platform | Config lines | Target |
|----------|-------------|--------|
| LINUX / Ubuntu | `CONFIG_BOARD_CHOICE_LINUX=y`<br>`CONFIG_BOARD_CHOICE_UBUNTU=y` | Native x86/x64 ELF on Ubuntu/Debian |
| LINUX / Raspberry Pi | `CONFIG_BOARD_CHOICE_LINUX=y`<br>`CONFIG_BOARD_CHOICE_RASPBERRY_PI=y` | Native ARM ELF on RPi |
| T5AI | `CONFIG_BOARD_CHOICE_T5AI=y` | Tuya T5AI MCU |
| ESP32 | `CONFIG_BOARD_CHOICE_ESP32=y` | Espressif ESP32 series |

Example for LINUX (the only platform that can compile and run natively on the host):

```
CONFIG_BOARD_CHOICE_LINUX=y
CONFIG_BOARD_CHOICE_UBUNTU=y
```

### Step 3: src/tuya_app_main.c

Entry source file **must be named `tuya_app_main.c`** (convention from the official template). It follows a dual-path entry pattern:

```c
#include "tal_api.h"
#include "tkl_output.h"

static void user_main(void)
{
    tal_log_init(TAL_LOG_LEVEL_DEBUG, 1024, (TAL_LOG_OUTPUT_CB)tkl_log_output);
    PR_DEBUG("hello world\r\n");

    while (1) {
        tal_system_sleep(1000);
    }
}

#if OPERATING_SYSTEM == SYSTEM_LINUX
void main(int argc, char *argv[])
{
    user_main();
}
#else

static THREAD_HANDLE ty_app_thread = NULL;

static void tuya_app_thread(void *arg)
{
    user_main();
    tal_thread_delete(ty_app_thread);
    ty_app_thread = NULL;
}

void tuya_app_main(void)
{
    THREAD_CFG_T thrd_param = {0};
    thrd_param.stackDepth = 1024 * 4;
    thrd_param.priority = THREAD_PRIO_1;
    thrd_param.thrdname = "tuya_app_main";
    tal_thread_create_and_start(&ty_app_thread, NULL, NULL, tuya_app_thread, NULL, &thrd_param);
}
#endif
```

Key points:
- `user_main()` contains all application logic
- On LINUX: `main()` calls `user_main()` directly (native process)
- On MCU: `tuya_app_main()` spawns a thread that calls `user_main()`
- `OPERATING_SYSTEM == SYSTEM_LINUX` (value 100) is set automatically by the LINUX platform Kconfig

### Step 4: Build and Run

```bash
cd <project_dir>
mkdir -p .cache && touch .cache/.dont_prompt_update_platform
tos.py build
./dist/<project>_<version>/<project>_<version>.elf   # LINUX only
```

## Updating Dependencies

```bash
tos.py update
```

Switches each platform submodule to its pinned commit (`$OPEN_SDK_ROOT/platform/platform_config.yaml`). Run after `git pull`.

## tos.py Command Reference

See `references/TOS_COMMANDS.md`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `tos.py new` hangs | Waiting for `input()` — interactive only | Use in a TTY terminal; cannot be automated |
| Project exists error on `new` | Directory already exists | Choose a different name or delete the existing directory |
| `config menu` arrow keys broken | Windows terminal compat | Use `h`/`j`/`k`/`l`; or switch between cmd/powershell |
| `could not lock config file` | Stale `~/.gitconfig.lock` | `rm ~/.gitconfig.lock` |
| No configs shown in `config choice` | No `config/` dir and no board configs for current platform | Create `app_default.config` manually or check platform setup |
| Build fails after `tos.py new` | No config selected yet | Run `tos.py config choice` or create `app_default.config` |
