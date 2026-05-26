---
name: tuyaopen/debug-helper
description: >-
  Agent-friendly non-blocking serial log capture for TuyaOpen devices.
  Runs tos.py monitor in the background, writes logs to file, and lets
  the agent tail or stop it at any time. Use when the agent needs to
  capture device logs without blocking, run a debug session, or monitor
  UART output during a build-flash-analyze loop.
  后台串口日志、非阻塞监控、设备日志捕获、agent日志分析。
license: Apache-2.0
compatibility:
  - TuyaOpen environment activated (export.sh / export.bat / export.ps1)
  - Device connected via USB serial
  - tos.py monitor supports -l/--log flag (TuyaOpen SDK current master)
---

# TuyaOpen Debug Helper

Provides non-blocking serial log capture for agents using `tos.py monitor -l`.
The monitor runs as a background subprocess; the agent reads log output from a
file and stops the process when done.

## Script location

```
.agents/skills/tuyaopen/debug-helper/scripts/monitor_helper.py
```

No extra dependencies — uses Python stdlib only.

## Quick usage

```bash
# Start background monitor (logs to <project_dir>/.target_logging/YYYYMMDD_HHMMSS.log)
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/debug-helper/scripts/monitor_helper.py start -p /dev/ttyACM1

# Read last 200 lines (JSON output for agent parsing)
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/debug-helper/scripts/monitor_helper.py --json tail -n 200

# Stop monitor (releases serial port)
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/debug-helper/scripts/monitor_helper.py stop
```

## Commands

| Command | Purpose |
|---------|---------|
| `start -p <port> [-l <logfile>]` | Launch `tos.py monitor -l` in background; auto-names log file if `-l` omitted |
| `tail [-n N]` | Read last N lines from log file (default 200) |
| `stop` | Terminate the monitor process; release serial port |
| `status` | Check whether monitor is running |

Add `--json` before the command for machine-readable output.

## Log file location

All logs and session state are written to **`<project_dir>/.target_logging/`**, where `<project_dir>` is the directory containing `app_default.config` (the TuyaOpen project root). The script finds this automatically by searching upward from the current working directory.

This location keeps logs with the project they belong to. The TuyaOpen SDK `.gitignore` contains `.target_logging` as an unanchored rule — it matches at any depth in the repository, so logs are always gitignored regardless of where the project lives under the SDK.

```
<project_dir>/                    e.g. apps/tuya_cloud/switch_demo/
└── .target_logging/              gitignored by SDK .gitignore
    ├── session.json              active monitor session (PID + log path)
    └── YYYYMMDD_HHMMSS.log       auto-named log file per session
```

## Session file

Session state (PID + log file path) is stored in `<project_dir>/.target_logging/session.json`.
Only one monitor session runs at a time — starting a new one automatically stops the previous.

## Port selection for T5 dual-UART boards

T5 / T5AI boards expose two serial ports (WCH dual-serial, VID `0x1a86` PID `0x55d2`):

- **Linux typical:** `ttyACM0` = flash, `ttyACM1` = monitor/log
- **Windows typical:** lower COM = flash, higher COM = monitor/log

These are common cases, not guarantees. If log output is absent or garbled after `start`, try the other port.

List available ports:

```bash
# Linux / macOS
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null

# Windows PowerShell
[System.IO.Ports.SerialPort]::GetPortNames()
```

## Typical agent workflow

```bash
# 1. Start background monitor
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/debug-helper/scripts/monitor_helper.py \
    --json start -p /dev/ttyACM1

# 2. Flash firmware (monitor keeps logging while flash runs on other port)
tos.py flash -p /dev/ttyACM0

# 3. Wait for boot, then read log
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/debug-helper/scripts/monitor_helper.py \
    --json tail -n 200

# 4. Analyze: look for [ty E], OPRT_ errors, "feed watchdog", "mqtt connected"

# 5. Stop when done
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/debug-helper/scripts/monitor_helper.py stop
```

## Log analysis patterns

| Pattern | Meaning | Action |
|---------|---------|--------|
| `[... ty E]` | Error-level log | Analyze message and source location |
| `[... ty W]` | Warning | Usually non-fatal; investigate if repeated |
| `feed watchdog` | Heartbeat (~10s) | **Normal** — device is alive |
| `OPRT_` + negative number | SDK operation failed | Look up in `references/ERROR_CODES.md` in `tuyaopen/dev-loop` |
| `mqtt connected` | Cloud connected | **Success** |
| No output after start | Wrong port or wrong baud | Swap ports; check baud rate |

## Related skills

- `tuyaopen/dev-loop` — full build→flash→monitor→analyze loop (calls this skill)
- `tuyaopen/device-auth` — serial port needed before writing auth credentials
