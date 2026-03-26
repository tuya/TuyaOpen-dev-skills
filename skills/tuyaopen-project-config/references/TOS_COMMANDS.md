# tos.py Command Reference

| Command | Interactive | Description |
|---------|:-----------:|-------------|
| `tos.py version` | No | Show version (git tag-commit) |
| `tos.py check` | No | Verify tool versions + download submodules |
| `tos.py new project` | **Yes** | Create new app project from template |
| `tos.py new board` | **Yes** | Create new board BSP |
| `tos.py new platform` | **Yes** | Scaffold new platform port |
| `tos.py config choice` | **Yes** | Select a verified config |
| `tos.py config menu` | **Yes** | Visual Kconfig editor |
| `tos.py config save` | **Yes** | Save current config as named preset |
| `tos.py build` | No | Build current project (see skill `tuyaopen-build`) |
| `tos.py build -v` | No | Build with verbose output |
| `tos.py clean` | No | Clean build artifacts (ninja clean) |
| `tos.py clean -f` | No | Full clean (delete `.build/`) |
| `tos.py flash` | **Yes** | Flash firmware (see skill `tuyaopen-flash-monitor`) |
| `tos.py monitor` | **Yes** | View device serial logs (see skill `tuyaopen-flash-monitor`) |
| `tos.py update` | No | Sync platform dependencies to pinned commits |
| `tos.py dev bac` | No | Build all configs (testing) |
| `tos.py idf <cmd>` | Varies | Pass-through to ESP-IDF `idf.py` (ESP32 only) |
| `tos.py -d <cmd>` | — | Run any command with debug logging |

## `tos.py new platform` Details

Scaffolds a new platform port with toolchain templates.

Flow:
1. Prompts for platform name.
2. Creates `platform/<name>/` with adapter templates and `.gitignore`.
3. Opens menuconfig to select platform capabilities.
4. Generates porting skeleton (`tuyaos_adapter/`) based on selected features.
5. Creates `boards/<name>/` with board Kconfig.

This is an advanced operation — see official docs for the full porting guide.
