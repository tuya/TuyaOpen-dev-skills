---
name: tuyaopen-cli-debug
description: >-
  Send commands to the TuyaOpen device serial CLI (tal_cli) over UART and
  capture responses. Use when the user wants to run CLI commands on a connected
  T5AI, ESP32, T2, T3, or LN882H board — such as sys_reset, kv_dump, fs_ls,
  or custom registered commands — without opening a foreground monitor.
  Auto-discovers the USB serial port and platform baud rate.
  设备CLI命令、串口命令、tal_cli、kv_dump、sys_reset、串口调试。
license: Apache-2.0
compatibility:
  - TuyaOpen environment activated (export.sh) — for firmware builds
  - Python 3 with pyserial (`pip install pyserial`)
  - USB serial device (T5AI, ESP32, T2/T3, LN882H)
  - Firmware built with CONFIG_ENABLE_SERIAL_CLI_CMD=y
---

# TuyaOpen CLI Debug

Sends commands to the TuyaOpen device CLI over UART and returns the response.
Useful for inspecting device state (heap, KV, filesystem, threads) without
holding a foreground terminal open.

## Prerequisites

1. **pyserial installed:**

   ```bash
   pip install pyserial
   ```

2. **Firmware built with CLI enabled** — verify your `app_default.config` has:

   ```
   CONFIG_ENABLE_SERIAL_CLI_CMD=y
   CONFIG_CLI_CMD_SYS=y       # sys_* commands
   CONFIG_CLI_CMD_FS=y        # fs_* filesystem commands
   CONFIG_CLI_CMD_KV=y        # kv_* key-value store commands
   ```

   After changing config: `tos.py clean -f && tos.py build && tos.py flash`

3. **Serial port access (Linux):**

   ```bash
   sudo usermod -aG dialout $USER   # then re-login or: newgrp dialout
   ```

## Quick start

```bash
# Discover available CLI commands (auto-detects port; baud is always 115200)
python skills/tuyaopen-cli-debug/cli_debug.py help

# Send a single command
python skills/tuyaopen-cli-debug/cli_debug.py send "sys_version"

# Force a specific port (useful if auto-pick chooses the wrong ACM port)
python skills/tuyaopen-cli-debug/cli_debug.py -p /dev/ttyACM0 send "kv_dump"

# List candidate serial ports (no connection)
python skills/tuyaopen-cli-debug/cli_debug.py list-ports

# JSON output for agent callers
python skills/tuyaopen-cli-debug/cli_debug.py --json help
```

## Sub-commands

| Sub-command | Description |
|-------------|-------------|
| `help` | Send `help` to the device and list all available CLI commands |
| `send <cmd>` | Send a single CLI command and return the response |
| `list-ports` | List candidate serial ports (VID/PID scored, no connection) |
| `raw <text>` | Send raw bytes without newline handling |

## Options reference

| Option | Default | Description |
|--------|---------|-------------|
| `-p, --port <dev>` | auto | Serial port (e.g. `/dev/ttyACM0`) |
| `-b, --baud <rate>` | **115200** | Baud rate. tal_cli hardcodes 115200 on every platform — do not override unless you have patched the SDK. |
| `--timeout <sec>` | 3.0 | Seconds to wait for CLI response |
| `--json` | off | Output results as JSON (stable keys: `ok`, `output`, `error`, `hint`) |
| `-v, --verbose` | off | Print port discovery and timing details to stderr |

## Baud rate

**Always 115200.** Hardcoded in `TuyaOpen/src/tal_cli/src/tal_cli.c:811`:

```c
cfg.base_cfg.baudrate = 115200;
```

This is platform-independent — T5AI, ESP32, T2, T3, LN882H all use 115200 for the
`tal_cli` UART. Don't confuse this with the platform-specific log/monitor baud
rate used by `tos.py monitor` (which can be 460800/921600 etc.); those use the
chip vendor's own UART driver, not `tal_cli`.

## T5AI dual-serial port selection

T5AI dev boards expose **two** USB-serial ports (WCH CH34x dual-serial):

- **Lower-numbered port** (e.g. `/dev/ttyACM0`) — typically flash port
- **Higher-numbered port** (e.g. `/dev/ttyACM1`) — typically log/monitor/CLI port

The script auto-picks the higher-numbered T5 port for CLI. Override with `-p` if
output is garbled or empty (some custom boards may swap the ports).

## Common CLI commands

The exact set depends on what your firmware registers. Typical built-in commands:

| Command | Description |
|---------|-------------|
| `help` | List all available commands |
| `sys_version` | Print firmware version string |
| `sys_reset` | Software reset the device |
| `kv_dump` | Dump all KV storage key-value pairs |
| `fs_ls /` | List files in the root filesystem |
| `fs_cat <path>` | Print file contents |
| `thread_list` | List running threads and stack usage |
| `heap_stats` | Print heap usage (free/total/peak) |
| `wifi_info` | Print WiFi connection status |

The actual commands your firmware exposes depend on:
- Which `CONFIG_CLI_CMD_*` options are enabled
- Which custom commands your app registers via `tal_cli_register_cmd()`

Run `help` first to discover what's available.

## Agent workflow example

```bash
# 1. Discover ports
python skills/tuyaopen-cli-debug/cli_debug.py --json list-ports

# 2. Check what commands are available
python skills/tuyaopen-cli-debug/cli_debug.py --json help

# 3. Send a debug command
python skills/tuyaopen-cli-debug/cli_debug.py --json send "heap_stats"

# 4. Reset the device remotely
python skills/tuyaopen-cli-debug/cli_debug.py --json send "sys_reset"
```

## CLI not enabled: firmware config

If `help` returns no output or the script reports `No response from device CLI`,
check whether the CLI is compiled in.

**Inspect the current build config:**
```bash
grep -i "ENABLE_SERIAL_CLI" dist/*/debug/*/sdkconfig 2>/dev/null
# Or check the source config:
grep "ENABLE_SERIAL_CLI" app_default.config
```

**Enable it:**
Edit `app_default.config` and add:
```
CONFIG_ENABLE_SERIAL_CLI_CMD=y
CONFIG_CLI_CMD_SYS=y
CONFIG_CLI_CMD_KV=y
CONFIG_CLI_CMD_FS=y
```

Then rebuild and reflash:
```bash
tos.py clean -f && tos.py build && tos.py flash
```

## JSON output (for agents)

All sub-commands support `--json`. Stable keys:

| Key | Type | Description |
|-----|------|-------------|
| `ok` | bool | True on success |
| `port` | str | Serial port used |
| `baud` | int | Baud rate used |
| `command` | str | CLI command sent |
| `output` | str | Cleaned response text (echo stripped) |
| `raw` | str | Full raw response bytes (decoded as UTF-8) |
| `error` | str | Error message (if `ok` is false) |
| `hint` | str | Actionable advice (if `ok` is false) |

## Port busy: detecting conflicts

If the port is held by another process (e.g. `tos.py monitor`, a foreground terminal):

```bash
# Find who's holding the port
fuser /dev/ttyACM1
lsof /dev/ttyACM1
```

Stop `tos.py monitor` (Ctrl+C then Enter) or `agent-hardware-debug-helper-tools`
service stop before using `cli_debug.py`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `No response from device CLI` | CLI not enabled in firmware | Add `CONFIG_ENABLE_SERIAL_CLI_CMD=y`, rebuild |
| `No response from device CLI` | Wrong port | Try the other ACM port with `-p /dev/ttyACM0` |
| `No response from device CLI` | Wrong baud rate | Check platform baud table; use `--baud` |
| `Cannot open /dev/ttyACM1` | Port held by another process | Stop `tos.py monitor`; `fuser /dev/ttyACM1` |
| `Cannot open /dev/ttyACM1` | Permission denied | `sudo usermod -aG dialout $USER` then re-login |
| `No serial port found` | Device not connected | Re-plug USB (data cable, not power-only) |
| Garbled output | Wrong baud rate | Use `--baud` with the correct rate for your platform |
| Response looks truncated | Command takes >3s | Increase `--timeout 10` |

## Related skills

- **`agent-hardware-debug-helper-tools`** — detached background logging, port discovery with JSON, `cli send` / `cli reboot` wrappers.
- **`tuyaopen-flash-monitor`** — `tos.py flash` and `tos.py monitor`; baud rates per chip.
- **`tuyaopen-crash-decode`** — decode PC/LR/stack addresses from crash dumps to source locations.
- **`tuyaopen-build`** — rebuild firmware with CLI enabled.

## Test result (connected T5AI board, 2025-06-25)

Port auto-discovery succeeded, identifying `/dev/ttyACM1` (VID 0x1a86, PID 0x55d2,
WCH CH34x dual-serial, score 65) as the T5AI monitor/CLI port. The `help` command
was sent at 460800 baud. The currently flashed DuckyClaw firmware does not have
`CONFIG_ENABLE_SERIAL_CLI_CMD=y` compiled in (the BK7258 native `CONFIG_CLI=y` is
present but that is the chip SDK's own CLI, not TuyaOpen's `tal_cli` interface). The
script correctly reported:

```json
{
  "ok": false,
  "error": "No response from device CLI.",
  "hint": "No data received. Possible causes:\n  1. CONFIG_ENABLE_SERIAL_CLI_CMD=y is not set...\n  ..."
}
```

To enable the CLI: add `CONFIG_ENABLE_SERIAL_CLI_CMD=y` to `app_default.config`,
then `tos.py clean -f && tos.py build && tos.py flash`. After reflash, `help` will
return the list of available commands.
