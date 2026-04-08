---
name: tuyaopen-dev-loop
description: >-
  Automated build-flash-monitor-analyze development loop for TuyaOpen devices.
  Covers log analysis, error patterns, CLI testing, and iterative debugging.
  Use when the user mentions dev loop, automated testing, log analysis, debug
  cycle, iterative development, or CI loop.
  开发闭环、自动化测试、日志分析、调试循环、迭代开发。
license: Apache-2.0
compatibility:
  - TuyaOpen environment activated (export.sh)
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

1. **Build**: `tos.py build` — compile firmware (see skill `tuyaopen-build`)
2. **Flash**: `tos.py flash` — deploy to device (see skill `tuyaopen-flash-monitor`); pass **`-p`** when tyutool would otherwise prompt for the port
3. **Monitor / capture logs**: `tos.py monitor` for interactive sessions, or **hands-off** **`agent_target_tool.py service start --detach`** → **`service tail`** / **`logs latest`** (JSON on stdout; see **`agent-hardware-debug-helper-tools`** → *Hands-off logging (for agent analysis)*)
4. **Analyze**: parse **`service tail`** `text` or the log file under **`.target_logging/`** for errors, warnings, crash indicators (patterns below)
5. **Decide**: pass (device healthy) or fail (fix code and restart loop)

### LINUX shortcut

For LINUX platform targets, skip flash/monitor — use the bundled script:

```bash
scripts/build_run_linux.sh          # build + run + auto-analyze (30s timeout)
scripts/build_run_linux.sh 60       # custom timeout in seconds
scripts/build_run_linux.sh 0        # no timeout (run until Ctrl+C)
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

Default level is typically `DEBUG`. Set via `tal_log_init(TAL_LOG_LEVEL_DEBUG, 1024, callback)`.

## CLI Testing

TuyaOpen includes a built-in CLI system (`tal_cli`) accessible via the debug UART (prompt: `tuya> `). For CLI commands, custom command registration, and batch testing details, see `references/ERROR_CODES.md`.

## Success / Failure Criteria

### Device is healthy when

- `feed watchdog` messages appear at regular intervals (~10 seconds)
- No `PR_ERR` messages after initialization completes
- MQTT connection established (for cloud-connected apps)
- CLI responds to commands (if CLI is enabled)

### Device has problems when

- **No serial output**: wrong port, wrong baud rate, device bricked, or crash before log init
- **Boot loop**: repeated startup messages without reaching main loop — likely crash in init
- **`PR_ERR` during runtime**: check the error message and source file:line for context
- **Watchdog timeout / reset**: device stopped feeding watchdog — likely deadlock or infinite loop
- **MQTT connection failures**: check network, credentials, PID mismatch
- **`OPRT_MALLOC_FAILED`**: memory exhaustion — reduce buffer sizes or check for leaks

## Agent Iteration Strategy

### On build failure

1. Read the compiler error output carefully.
2. Identify the source file and line.
3. Fix the code.
4. `tos.py build` again. Repeat until build succeeds.

### On flash failure

1. Check serial port (see skill `tuyaopen-flash-monitor` for T5 dual-port strategy).
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

1. Verify serial port and baud rate match the chip (see skill `tuyaopen-flash-monitor`).
2. Reset the device manually.
3. If still no output, the firmware may have crashed before log init — review recent code changes.

## AI agent helper: `agent-hardware-debug-helper-tools` (`agent_target_tool.py`)

Full reference: skill **`agent-hardware-debug-helper-tools`**. Script path (relative to **TuyaOpen repo root**):

`.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py`

The tool resolves the repo root by searching for **`tos.py`** (not by path depth). Logs and session files always sit under **`<repo>/.target_logging/`**, independent of your shell current directory.

Cross-platform helper for **listing USB serial ports**, **background logging** to `.target_logging/<date>/<timestamp>.log`, and **optional non-blocking UART CLI injection** when the firmware exposes `tal_cli` / test commands over the debug UART. Default profile is **Tuya T5 / T5AI** (`--target tuya_t5`, monitor baud 460800).

**Dependency:** `pip install -r .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool_requirements.txt` (`pyserial`).

**T5 USB–UART:** Official T5 / T5AI dev boards normally use a **WCH CH34x dual-serial** bridge with **VID `0x1a86`** and **PID `0x55d2`**. `pick-port` and `service start` (without `--port`) look for this pair; if it is missing, JSON returns **`error`: `device_not_found`**, **`reason_code`**, and **`discovery_log`**. Use **`-v` / `--verbose`** on stderr (safe with `--json`). **`--allow-any-serial`** is only for non-standard bridges.

**Typical flow** (`<REPO>` = repo root; from `<REPO>` you can use paths as below):

1. `python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json list-devices`
2. `python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py -v --json pick-port`
3. **One-shot debug capture (preferred when analyzing a fresh boot log):**  
   `python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json debug-session run`  
   Starts detached logging, sends a **CLI `reboot`** by default (or `--hw-reset` for a DTR/RTS pulse), waits **`--boot-wait`** seconds, then returns JSON with **`log_file`**. If a logging session is already running, it is **stopped automatically** (single instance); JSON may include **`replaced_previous_session`: true**.
4. `python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json service tail -n 200` — read buffered log.
5. **(Optional)** `cli help` / `cli send` / `cli reboot` — only if the **built firmware** registers UART CLI or test hooks; skip otherwise and rely on logs + reset (`debug-session run` with **`--no-cli-reboot`** / **`--hw-reset`** as appropriate).
6. `python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json logs latest` — resolve **newest** `*.log` under `.target_logging/` (also **`recommended`** in JSON).
7. `python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json service stop` — release serial port.

**Manual equivalent of step 3** (if not using `debug-session run`):  
`service start --detach` → reset (hardware or CLI, if applicable) → **`service tail`** → **optional CLI** → **`service stop`**.

Session metadata: **`<repo>/.target_logging/session.json`** (at most one active service; restarting replaces it). Each new logging run updates **`<repo>/.target_logging/LATEST_LOG`**. Timed logging: `service start --duration SEC` or `debug-session run --duration SEC`.

### Iteration loop (analyze → fix → re-run)

Repeat until logs are clean:

1. **Build** → **flash** (see `tuyaopen-build` / `tuyaopen-flash-monitor`).
2. **`debug-session run`** (or `service start --detach` + reset) to capture a **full boot + runtime** trace.
3. **`service tail`** / read **`logs latest`** → search `ty E`, `OPRT_`, watchdog, MQTT (see [Log Format](#log-format--patterns) above).
4. **(Optional)** **`cli help`** / **`cli send`** — only if the app implements **UART CLI test functions**; otherwise infer behavior from logs alone or add CLI commands in firmware first.
5. Edit code → go to step 1.
6. **`service stop`** when done so the port is free for the next flash.

**`tos.py` wrappers** (from an app directory, pass **`--project-dir .`**):

- `python <path-to-repo>/.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --project-dir . flash -p /dev/ttyACM0`
- `python <path-to-repo>/.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --project-dir . monitor -p /dev/ttyACM1`

Dual UART (T5): see **`tuyaopen-flash-monitor`**. Use **`service start`** on the **monitor** port; **`flash`** on the programming port.
