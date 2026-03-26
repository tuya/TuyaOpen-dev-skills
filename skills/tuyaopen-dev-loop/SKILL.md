---
name: tuyaopen-dev-loop
description: >-
  Automated build-flash-monitor-analyze development loop for TuyaOpen devices.
  Covers log analysis, error patterns, CLI testing, and iterative debugging.
  Use when the user mentions dev loop, automated testing, log analysis, debug
  cycle, iterative development, or CI loop.
  开发闭环、自动化测试、日志分析、调试循环、迭代开发。
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
2. **Flash**: `tos.py flash` — deploy to device (see skill `tuyaopen-flash-monitor`)
3. **Monitor**: `tos.py monitor` — capture serial log output
4. **Analyze**: parse logs for errors, warnings, crash indicators
5. **Decide**: pass (device healthy) or fail (fix code and restart loop)

### LINUX shortcut

For LINUX platform targets, skip flash/monitor — run the ELF binary directly and capture stdout:

```bash
./.build/bin/<project>_<version> 2>&1 | tee device.log
```

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
| `OPRT_` followed by negative number | SDK operation failed | Look up error code (see table below) |
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

### Overview

TuyaOpen includes a built-in CLI system (`tal_cli`) accessible via the debug UART. The CLI prompt is `tuya> `.

### Using CLI via monitor

1. Start monitor: `tos.py monitor` (use the correct baud rate for your chip — see skill `tuyaopen-flash-monitor`)
2. Type commands at the `tuya> ` prompt
3. CLI supports tab completion and command history (up/down keys)

### Built-in commands

| Command | Description | Requires |
|---------|-------------|----------|
| `help` | List all registered commands | `tal_cli_init()` |
| `auth <uuid> <authkey>` | Write device credentials | `tuya_authorize_init()` |
| `auth-read` | Read stored credentials | `tuya_authorize_init()` |
| `auth-reset` | Clear stored credentials | `tuya_authorize_init()` |

### Registering custom CLI commands

Applications can register custom test commands:

```c
static void my_test_cmd(int argc, char *argv[]) {
    PR_DEBUG("test command executed, argc=%d", argc);
}

static const cli_cmd_t my_cmds[] = {
    { .name = "mytest", .help = "run my test", .func = my_test_cmd },
};

tal_cli_cmd_register(my_cmds, sizeof(my_cmds) / sizeof(my_cmds[0]));
```

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
3. Map error codes using the table below.
4. Identify the source file and line from the log.
5. Fix the code based on the error context.
6. Restart the loop: build → flash → monitor.

### On no output

1. Verify serial port and baud rate match the chip (see skill `tuyaopen-flash-monitor`).
2. Reset the device manually.
3. If still no output, the firmware may have crashed before log init — review recent code changes.

## Common Error Codes

| Code | Name | Value | Typical cause |
|------|------|-------|---------------|
| `OPRT_OK` | Success | 0 | — |
| `OPRT_COM_ERROR` | General error | -1 | Catch-all failure |
| `OPRT_INVALID_PARM` | Invalid parameter | -2 | NULL pointer or out-of-range argument |
| `OPRT_MALLOC_FAILED` | Allocation failed | -3 | Out of memory |
| `OPRT_NOT_SUPPORTED` | Not supported | -4 | Feature disabled or platform mismatch |
| `OPRT_NETWORK_ERROR` | Network error | -5 | WiFi disconnected or DNS failure |
| `OPRT_NOT_FOUND` | Not found | -6 | Missing resource, file, or config |

Full error code definitions: `src/common/include/tuya_error_code.h`

## Batch Testing

### Build all configs

```bash
tos.py dev bac                    # build every config in the project
tos.py dev bac --dist ./output    # save binaries to output dir
tos.py dev bac -o ./logs          # save build logs
```

Useful for regression testing across all supported board configurations.
