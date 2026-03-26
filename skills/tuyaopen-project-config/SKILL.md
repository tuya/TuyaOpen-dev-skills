---
name: tuyaopen-project-config
description: >-
  Create new TuyaOpen projects, boards, and platforms, manage build
  configurations, update platform dependencies, and use tos.py subcommands.
  Use when the user mentions creating a project, tos.py new, saving or
  choosing a config, tos.py update, or general tos.py usage.
  创建项目、新建工程、新建开发板、配置管理、保存配置、选择配置、更新依赖。
license: Apache-2.0
compatibility:
  - TuyaOpen environment activated (export.sh)
  - TTY terminal required for interactive commands (tos.py new, config choice/menu/save)
---

# TuyaOpen Project & Config Management

Docs: <https://tuyaopen.ai/zh/docs/tos-tools/tos-guide>

## Creating a New Project

> All `tos.py new` subcommands are **interactive** (use `input()` / menu prompts). They require a TTY and cannot be used in non-interactive Agent/CI pipelines.

### `tos.py new project` (interactive)

Creates a new application from a template **in the current working directory**.

```bash
cd apps/my_category          # navigate to where you want the project
tos.py new                   # defaults to base framework
tos.py new --framework arduino   # Arduino-style project
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
2. Select a config: `tos.py config choice` (interactive), or manually create `app_default.config` (see skill `tuyaopen-build` for Kconfig format).
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

See skill `tuyaopen-add-board` for the full board adaptation guide.

## Configuration Management

For detailed Kconfig editing guidance (dependency mechanisms, defconfig format, config pipeline), see skill **`tuyaopen-build`**.

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

Opens a terminal-based Kconfig editor. **Triggers a full clean first.** Best for fine-tuning options with complex dependencies — the editor resolves `select` / `depends on` automatically. See skill `tuyaopen-build` for the Kconfig Dependency Guide.

### `tos.py config save` (interactive)

```bash
tos.py config save
```

Prompts for a name, then copies current `app_default.config` to the project's `config/` directory as a named preset. Useful after customizing with `config menu`.

### Non-Interactive Config (Agent / CI)

Edit `app_default.config` directly — no TTY needed. This is the recommended approach for automated workflows. See skill `tuyaopen-build` for format details and Kconfig dependency handling.

## Updating Dependencies

```bash
tos.py update
```

Reads `platform/platform_config.yaml` and switches each platform submodule to its pinned commit. Run after `git pull` or `git checkout` on the main repo.

## tos.py Command Reference

For the complete tos.py command table (all subcommands, interactive flags, descriptions), see `references/TOS_COMMANDS.md`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `tos.py new` hangs | Waiting for `input()` — interactive only | Use in a TTY terminal; cannot be automated |
| Project exists error on `new` | Directory already exists | Choose a different name or delete the existing directory |
| `config menu` arrow keys broken | Windows terminal compat | Use `h`/`j`/`k`/`l`; or switch between cmd/powershell |
| `could not lock config file` | Stale `~/.gitconfig.lock` | `rm ~/.gitconfig.lock` |
| No configs shown in `config choice` | No `config/` dir and no board configs for current platform | Create `app_default.config` manually or check platform setup |
| Build fails after `tos.py new` | No config selected yet | Run `tos.py config choice` or create `app_default.config` |
