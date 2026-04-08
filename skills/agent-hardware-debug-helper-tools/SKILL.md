---
name: agent-hardware-debug-helper-tools
description: >-
  AI-agent serial helper for TuyaOpen hardware: list USB ports (T5 VID/PID),
  background logging, tail logs, optional UART CLI injection when firmware
  exposes tal_cli / test commands, and wrap tos.py flash/monitor. Use when the
  user mentions agent_target_tool, serial monitor service, hardware CLI,
  hands-off logging, detached service, service tail, logs latest,
  .target_logging, pick-port, or agent-friendly device discovery.
  串口、可选硬件CLI、日志后台、设备枚举、agent_target_tool。
license: Apache-2.0
compatibility:
  - TuyaOpen repository clone (tos.py at repo root)
  - Python 3 with pyserial
  - USB serial device (MCU targets)
---

# Agent hardware debug helper tools

**UART CLI is optional.** Use `cli send`, `cli help`, and `cli reboot` only when the **firmware under test** enables the debug UART CLI (`tal_cli`, `tuya>` prompt, or custom test commands). If the app does not register CLI commands, rely on **log capture alone** (`service start`, `service tail`, `debug-session run` with **`--no-cli-reboot`** / **`--hw-reset`** as needed). The AI should add CLI-based tests in firmware only when that matches the product; the tool does not require CLI for a valid debug workflow.

## Script location (single copy)

| Item | Path (relative to TuyaOpen repo root) |
|------|----------------------------------------|
| Tool | `.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py` |
| Dependencies | `.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool_requirements.txt` (`pyserial` + `pytest` for tests) |

The script **does not** assume a fixed folder depth: it finds the repo root by searching **upward for `tos.py`**. Session and logs always use:

- **`<repo>/.target_logging/`** — dated log files and `session.json` (not relative to CWD).

Install once:

```bash
pip install -r .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool_requirements.txt
```

## When to use

- **Dev loop** (`tuyaopen-dev-loop`): detached logging while iterating; tail errors; **optionally** `cli send` / `cli help` **if** the build exposes a UART CLI.
- **Flash & monitor** (`tuyaopen-flash-monitor`): enumerate ports with **VID 0x1a86 / PID 0x55d2** (T5 default WCH dual-serial); pick monitor vs flash port heuristics.
- **Device auth** (`tuyaopen-device-auth`): resolve the **correct serial port** before interactive auth / provisioning over UART (provisioning may use serial **without** generic `tal_cli` test hooks).

## Hands-off logging (for agent analysis)

Use this instead of foreground **`tos.py monitor`** when the agent must **stay non-blocking**, get **machine-readable paths**, and **read log text from JSON** (`--json` on every step).

**Why:** Foreground `monitor` blocks the terminal; **`service start --detach`** runs a background logger with a TCP control channel so **`service tail`**, **`logs latest`**, and **`service ping`** return JSON on stdout while firmware keeps printing to a file under **`.target_logging/`**.

**Typical T5 dual-UART:** after **`pick-port`** / **`list-devices`**, pass **`-p`** explicitly — often **lower `ttyACM` = flash**, **higher = log/monitor** (not guaranteed; swap if empty or wrong baud).

| Step | Command (from `<REPO>`) | Agent use |
|------|-------------------------|-----------|
| 1 | `python …/agent_target_tool.py --json service start --detach -p /dev/ttyACM1 --log-suffix "what_you_tested"` | Read **`log_file`** / **`session.serial_port`** / **`control_port`**; confirm **`ok: true`**. |
| 2 | `python …/agent_target_tool.py --json service ping` | Verify **`message": "pong"`** before tail. |
| 3 | `python …/agent_target_tool.py --json service tail -n 200` | Read **`text`** — raw UART lines (may include ANSI). Search boot errors, **`feed watchdog`**, `PR_ERR`, `OPRT_` (see **`tuyaopen-dev-loop`** log patterns). |
| 4 | `python …/agent_target_tool.py --json logs latest` | Resolve path: **`recommended`** or **`latest_log_by_mtime`** for file-based analysis / attaching to reports. |
| 5 | `python …/agent_target_tool.py --json service stop` | Releases serial port; **`ok: true`** expected. |

**One-shot alternative:** **`debug-session run`** combines start + optional reset + boot wait + returns **`log_file`** in one JSON response (see table below).

**Analyzing `service tail` `text`:** Treat as firmware console output. Prefer line-based scanning; strip ANSI escape sequences if you need plain text. Correlate with **`tuyaopen-dev-loop`** (e.g. healthy device often shows **`feed watchdog`** periodically). If **`no_active_session`**, run step 1 again (after **`list-devices`** confirms the port).

## Command examples

Replace `<REPO>` with your TuyaOpen clone path, or `cd` to `<REPO>` and use the relative path.

### Full logging debug process (AI-friendly)

**Minimum workflow:** discover → start logging → reset/capture boot → tail → **`logs latest`** → stop. **CLI steps below are optional** (only if the firmware implements UART CLI / test commands).

| Phase | Command (from `<REPO>`) |
|-------|-------------------------|
| Discover | `python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py -v --json pick-port` |
| **One-shot start + reset + wait** | `python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json debug-session run` |
| **Label this capture (optional)** | Add **`--log-suffix "what changed"`** to **`service start`** or **`debug-session run`** — embeds a sanitized note in the log filename (JSON: **`log_name_suffix`**, **`log_suffix_note`**). |
| | Default soft reset uses **CLI `reboot`**; use **`--no-cli-reboot`** and/or **`--hw-reset`** when CLI reboot is unwanted or unavailable. |
| | `--boot-wait 4` (default). Only one logging service at a time: starting again **stops the previous** session automatically. |
| Read log | `python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json service tail -n 200` |
| **Optional — UART CLI** (if `tal_cli` / app-registered commands exist) | `cli help`, `cli send --line "…"`, `cli reboot` |
| **Newest log file path** | `python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json logs latest` → **`recommended`** / **`latest_log_by_mtime`** |
| Stop | `python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json service stop` |

`debug-session run` starts the same **detached** logging service as `service start --detach`; it then applies **reset** (CLI and/or hardware), waits, and returns JSON including **`log_file`**. The control channel **`hw_reset`** (DTR/RTS) does not depend on firmware CLI.

### Other commands

```bash
# From repo root (<REPO>)
python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py -v --json list-devices
python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py -v --json pick-port

python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json service start --detach --log-suffix "my_change_summary"
python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json service tail -n 100
python .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json service stop
```

**`tos.py` wrappers** (must run with project dir = app containing `app_default.config`):

```bash
cd apps/your_app
python ../../.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --project-dir . flash -p /dev/ttyACM0
python ../../.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --project-dir . monitor -p /dev/ttyACM1
```

(Adjust `../../` if your app lives deeper under `apps/`.)

**Flash / monitor via this wrapper:** `tyutool` output streams to the terminal as it runs (the wrapper does not buffer it). A long flash is normal; without `-p`, port auto-detect can also take a while — use **`pick-port`** / **`list-devices`** and pass **`-p`** explicitly when possible.

## Related skills

- **`tuyaopen-dev-loop`** — full build → flash → monitor → analyze loop; integrates this tool.
- **`tuyaopen-flash-monitor`** — `tos.py flash` / `tos.py monitor`; dual-port T5 strategy.
- **`tuyaopen-device-auth`** — UUID / AuthKey / provisioning; use `list-devices` / `pick-port` first.
- **`tuyaopen-env-setup`** — activate SDK / Python env when `tos.py` fails with missing modules (e.g. `click_completion`).

## Error cookbook (for agents)

Use the tool’s **`error_code`** to keep explanations accurate. Map each code to a friendly label, one first step, and escalation.

| `error_code` | User-friendly label | First thing to try | Escalation |
|--------------|---------------------|--------------------|------------|
| `no_serial_ports` | Board not seen on USB | Re-plug USB (data cable), try another port | Linux: `dialout` group; reinstall USB–UART driver |
| `t5_default_uart_not_found` | Serial exists but not the T5 bridge | Connect the T5 board; confirm VID **0x1a86** / PID **0x55d2** on `list-devices` | **`--allow-any-serial`** for non-WCH adapters only; see **`tuyaopen-flash-monitor`** for ACM0 vs ACM1 |
| `device_not_found` | Same family as above (pick/start) | Same as `no_serial_ports` / `t5_default_uart_not_found` depending on `reason_code` | Read **`discovery_log`** in JSON |
| `pyserial_missing` | Python serial library missing | `pip install -r .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool_requirements.txt` | Re-run the same command |
| `no_active_session` | Background logger not running | `python …/agent_target_tool.py --json service start --detach` (after `list-devices`) | Not an emergency—normal if you have not started logging yet |
| `no_logging_session` | Nothing to stop | Ignore or run `service stop` anyway (idempotent success) | — |
| `control_channel_error` | Lost contact with logger | Unplug/replug USB; `service stop` then `service start --detach` | Kill stale process holding the port |
| `control_server_timeout` | Logger slow to answer | Wait 2s; reconnect USB; retry `debug-session run` | Close other serial monitors |
| `session_not_ready_after_start` | Detached worker did not write session | Retry start; check USB | Same as `control_channel_error` |
| `no_log_files` | No captures yet under `.target_logging/` | Start logging, then `logs latest` again | — |
| `tos_py_not_found` | Not inside TuyaOpen clone | `cd` to repo root (directory with **`tos.py`**) | — |
| `tos_env_incomplete` | `tos.py` failed (missing deps / wrong Python) | Follow **`tuyaopen-env-setup`** / `export.sh`; install deps | Read JSON **`agent_hint`** / optional **`stderr_tail`** |
| `tos_failed` | `tos.py` failed for other reasons | Scroll up for flash/monitor output (**`stderr_tail`** may be empty when streamed) | **`tuyaopen-env-setup`** if toolchain unclear |
| `serial_open_failed` | Cannot open serial port | Close other apps using the port; unplug/replug | Linux: permissions / `dialout`; **`lsof`** on the device |
| `rpc_error` | Control command failed | `service ping`; if fail, restart logging session | See **`detail`** in JSON |
| `unknown_op` | Invalid control opcode (internal) | Use supported ops: ping, tail, cli_send, hw_reset, stop | Rare |

## How agents should talk to the user (vibe-friendly)

When interpreting JSON (especially errors):

1. **TL;DR first** — one plain sentence (not raw JSON keys).
2. **Then** paraphrase **`agent_hint`** as the concrete next step.
3. On **success** with **`log_file`** or **`recommended`**, offer **one** follow-up command (e.g. `service tail -n 200` or `logs latest`).
4. On **`no_active_session`**, stay calm: say the logger is not running and give a **single** start command—do not sound like a hard failure.

This keeps chat natural while the tool stays machine-readable on stdout.

## Automated tests

Pytest suite (no USB hardware required for most cases; CLI smoke uses the real repo):

```bash
pip install -r .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool_requirements.txt
pytest -q .agents/skills/agent-hardware-debug-helper-tools/tests
```

Tests live in **`.agents/skills/agent-hardware-debug-helper-tools/tests/test_agent_target_tool.py`**.

## Behaviour notes

- **JSON for agents:** Responses use stable keys: **`error_code`**, **`agent_hint`** (actionable text for the user), and where relevant **`hardware_connected`** / **`t5_target_connected`**. **`list-devices`** exits **1** with **`ok: false`** when no serial ports exist ( **`error_code`: `no_serial_ports`** ) so disconnected hardware is explicit. **`service stop`** with no session exits **0** and **`ok: true`** with **`error_code`: `no_logging_session`** (idempotent). Errors from **`service tail`** / **`cli *`** without an active session include **`error_code`: `no_active_session`**.
- **Log filename suffix:** **`--log-suffix TEXT`** on **`service start`** / **`debug-session run`** appends a sanitized label to the log name (`YYYYMMDD_HHMMSS_<suffix>.log`). Success JSON may include **`log_name_suffix`** (sanitized) and **`log_suffix_note`** (original request, truncated) so agents can record what the capture was for.
- **Single logging instance:** At most one **background** logging service. A new **`service start`** or **`debug-session run`** stops any **existing** session (control **stop** + PID kill) and starts fresh. Stale **`session.json`** entries (dead PID) are removed automatically. Success JSON may include **`replaced_previous_session`**.
- **`service stop`:** Runs **`cleanup_stale_session_file()`** first, then best-effort control **stop**, PID kill, and clears **`session.json`**. Returns exit **0** with **`control_stop_ok`** false if the TCP control server was unreachable (stale or crashed logger).
- **T5 default bridge:** VID `0x1a86`, PID `0x55d2`. Missing device → JSON `device_not_found` + `discovery_log` (see dev-loop skill).
- **Verbose:** `-v` logs to **stderr** only; safe with `--json` on stdout.
- **CLI injection:** Only use when the **running firmware** exposes a debug CLI; otherwise skip `cli *` and use logs + physical/`--hw-reset` reset only.
