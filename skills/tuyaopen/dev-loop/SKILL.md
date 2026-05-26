---
name: tuyaopen/dev-loop
description: >-
  Automated build-flash-monitor-analyze development loop for TuyaOpen devices.
  Covers log analysis, error patterns, CLI testing, and iterative debugging.
  Use when the user mentions dev loop, automated testing, log analysis, debug
  cycle, iterative development, or CI loop.
  开发闭环、自动化测试、日志分析、调试循环、迭代开发。
license: Apache-2.0
compatibility:
  - TuyaOpen environment activated (export.sh / export.ps1 / export.bat)
  - Device connected via USB (MCU targets) or native Linux host
---

# TuyaOpen Build-Deploy-Debug Loop

## Loop Workflow

The standard development iteration cycle for TuyaOpen hardware:

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│  Build  │────>│  Flash  │────>│ Monitor │────>│ Analyze │────>│ Decide  │
│         │     │         │     │  Logs   │     │ Results │     │         │
└─────────┘     └─────────┘     └─────────┘     └─────────┘     └────┬────┘
     ^                                                               │
     │                         ┌──────────┐                          │
     └─────────────────────────│ Fix Code │<─────── if error ────────┘
                               └──────────┘         if ok → done
```

### Step-by-step

1. **Build**: `tos.py build` — compile firmware (see skill `tuyaopen/build`)
2. **Flash**: Flash firmware to the device from the project directory:

   ```bash
   tos.py flash -p <port>        # specify port (recommended)
   tos.py flash                   # auto-detect port
   tos.py flash -p <port> -d      # debug output
   ```

   **T5 dual serial ports:** T5/T5AI boards expose two serial ports. Typical mapping (not guaranteed):
   - Linux: flash = `ttyACM0`, monitor/log = `ttyACM1`
   - Windows: flash = lower COM number, monitor/log = higher COM number

   If flash fails on one port, swap to the other. Serial permission required on Linux (once): `sudo usermod -aG dialout $USER` then reboot.

3. **Monitor / capture logs**: `tos.py monitor -p <port>` for interactive sessions, or **hands-off** background logging via `tuyaopen/debug-helper` (`monitor_helper.py start -p <port>` → `tail` → `stop`).
4. **Analyze**: read the log file under **`<project_dir>/.target_logging/`** for errors, warnings, crash indicators (patterns below)
5. **Decide**: pass (device healthy) or fail (fix code and restart loop)

### LINUX shortcut

For LINUX platform targets, skip flash/monitor — use the bundled script:

```bash
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/dev-loop/scripts/build_run.py          # build + run + auto-analyze (30s timeout)
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/dev-loop/scripts/build_run.py 60       # custom timeout in seconds
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/dev-loop/scripts/build_run.py 0        # no timeout
```

Or manually:

```bash
./dist/<project>_<version>/<project>_<version>.elf 2>&1 | tee device.log
```

Both `dist/` (canonical output) and `.build/bin/` (build intermediate) contain the ELF. Use `dist/` for consistency.

## Log Format & Patterns

### TuyaOpen log format

```
[MM-DD HH:MM:SS ty X][source_file.c:line] message
```

Where `X` is the log level: `E` (error), `W` (warn), `N` (notice), `I` (info), `D` (debug), `T` (trace).

### Key patterns to watch

| Pattern | Meaning | Action |
|---------|---------|--------|
| `[... ty E]` | Error-level log (`PR_ERR`) | Analyze the error message and source location |
| `[... ty W]` | Warning (`PR_WARN`) | Usually non-fatal but worth investigating |
| `feed watchdog` | Health monitor heartbeat (every ~10s) | **Normal** — device is alive |
| `OPRT_` followed by negative number | SDK operation failed | Look up error code (see `references/ERROR_CODES.md`) |
| `mqtt connected` or `MQTT_CONNECTED` | Cloud connection established | **Success** — device is online |
| `TUYA_EVENT_DIRECT_MQTT_CONNECTED` | Direct MQTT event | Cloud connection confirmed |
| `Replace the TUYA_OPENSDK_UUID` | Placeholder credentials detected | User must configure real UUID/AuthKey |
| No output after flash | Device crashed or wrong serial port | Check baud rate and port; try reset |
| Repeated reset / boot loop | Crash during init or watchdog timeout | Check last error before reset |
| `malloc failed` or `OPRT_MALLOC_FAILED` | Out of memory | Reduce buffer sizes or optimize memory |

### Log level hierarchy

```
ERR > WARN > NOTICE > INFO > DEBUG > TRACE
```

Default log level: `DEBUG`. Set via `tal_log_init(TAL_LOG_LEVEL_DEBUG, 1024, callback)`.

## CLI Testing

Built-in CLI (`tal_cli`) via debug UART (prompt: `tuya> `). Commands, registration, batch testing: `references/ERROR_CODES.md`.

## Device State

| State | Signal |
|-------|--------|
| Healthy | `feed watchdog` every ~10s; no `PR_ERR` after init; `mqtt connected` |
| No output | Wrong port, wrong baud, crash before log init |
| Boot loop | Crash in init — check last error before reset |
| Watchdog reset | Deadlock or infinite loop — check `PR_ERR` before reset |
| MQTT fail | Check network, credentials, PID mismatch |
| `OPRT_MALLOC_FAILED` | OOM — reduce buffer sizes |

## Agent Iteration Strategy

### On build failure

1. Read the compiler error output carefully.
2. Identify the source file and line.
3. Fix the code.
4. `tos.py build` again. Repeat until build succeeds.

### On flash failure

1. Check serial port (T5 dual-port: try the other port if flash fails — see the Flash step above).
2. Wait ~1 minute if port is busy.
3. Retry with the other port if available.
4. If still failing, ask the user to check hardware connection.

### On runtime error (log analysis)

1. Capture log output after flash (monitor for 10-30 seconds).
2. Search for `ty E` (errors) and `OPRT_` patterns.
3. Map error codes using `references/ERROR_CODES.md`.
4. Identify the source file and line from the log.
5. Fix the code based on the error context.
6. Restart the loop: build → flash → monitor.

### On no output

1. Verify serial port and baud rate match the chip (check the baud rate table: T2=115200, T3/T5AI=460800, ESP32=115200, LN882H=921600).
2. Reset the device manually.
3. If still no output, the firmware may have crashed before log init — review recent code changes.

## AI agent helper: `tuyaopen/debug-helper` (`monitor_helper.py`)

Full reference: skill **`tuyaopen/debug-helper`**. Script path (relative to SDK root):

`.agents/skills/tuyaopen/debug-helper/scripts/monitor_helper.py`

Logs are always written to **`<project_dir>/.target_logging/`** (gitignored by the SDK).

### Typical flow

```bash
# 1. Start background monitor (non-blocking)
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/debug-helper/scripts/monitor_helper.py \
    --json start -p /dev/ttyACM1

# 2. Flash on the other port while monitor keeps logging
tos.py flash -p /dev/ttyACM0

# 3. Read log after boot
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/debug-helper/scripts/monitor_helper.py \
    --json tail -n 200

# 4. Stop and release port
$OPEN_SDK_PYTHON .agents/skills/tuyaopen/debug-helper/scripts/monitor_helper.py stop
```

### Iteration loop (analyze → fix → re-run)

Repeat until logs are clean:

1. **Build** → **`tos.py flash -p <port>`**
2. **`monitor_helper.py start -p <monitor-port>`** — capture boot + runtime trace
3. **`monitor_helper.py tail -n 200`** → search `ty E`, `OPRT_`, watchdog, MQTT
4. Edit code → go to step 1
5. **`monitor_helper.py stop`** when done so the port is free for the next flash
