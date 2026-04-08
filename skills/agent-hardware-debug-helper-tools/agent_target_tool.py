#!/usr/bin/env python3
# coding=utf-8
"""
agent_target_tool.py — Cross-platform TuyaOpen hardware helper for AI agents (Cursor / Claude Code).

Repository layout: this file lives under
  <TuyaOpen>/.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py
It resolves the TuyaOpen root by searching upward for tos.py. Logs and session data go to
  <TuyaOpen>/.target_logging/
regardless of the current working directory.

Features:
  - List USB serial devices (VID:PID, manufacturer, product, port name)
  - Background logging to .target_logging/<date>/<timestamp>.log
  - Local control channel so the agent can tail logs and optionally inject UART CLI without blocking
  - cli send | cli help | cli reboot — optional; only if firmware exposes tal_cli / debug CLI (needs active service)
  - debug-session run — start detached monitor, optional HW DTR reset or CLI reboot, boot wait
  - logs latest — path to newest log (and LATEST_LOG pointer)
  - Wrappers for tos.py flash / monitor (use --project-dir for the app tree)
  - Pluggable targets (default: Tuya T5 / T5AI-style UART)

Usage (REPO = TuyaOpen clone root):
  python REPO/.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json list-devices
  python REPO/.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json debug-session run
  python REPO/.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json service start --detach --log-suffix "fix_led_ripple"
  python REPO/.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py --json logs latest
  (from an app dir with app_default.config, pass e.g. --project-dir .)

Requires: pip install -r REPO/.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool_requirements.txt
  (pyserial for runtime; pytest in same file for unit tests)
"""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Optional: pyserial
# ---------------------------------------------------------------------------
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None  # type: ignore
    list_ports = None  # type: ignore


def _repo_root() -> Path:
    """
    TuyaOpen repository root: first directory upward from this file that contains tos.py.

    This script may live at .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py (or elsewhere
    under the tree); anchoring on tos.py keeps paths stable.
    """
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "tos.py").is_file():
            return parent
    raise RuntimeError(
        f"Could not find TuyaOpen repository root (no tos.py found above {here}). "
        "Keep this script inside the TuyaOpen clone."
    )


def _out(obj: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False), flush=True)
    else:
        if obj.get("ok"):
            print("OK:", obj.get("message", ""), file=sys.stderr)
        else:
            print("ERROR:", obj.get("error", "unknown"), file=sys.stderr)
            hint = obj.get("agent_hint")
            if isinstance(hint, str) and hint.strip():
                print("Hint:", hint.strip(), file=sys.stderr, flush=True)


def _vlog(verbose: bool, message: str) -> None:
    """Human-readable progress on stderr (does not pollute --json stdout)."""
    if verbose:
        print(f"[agent_target_tool] {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Hardware targets: see hardware_target_base.py, target_t5.py (future: e.g. target_raspi5.py)
# ---------------------------------------------------------------------------
_SKILLS_DIR = Path(__file__).resolve().parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from hardware_target_base import HardwareTarget, PortInfo, TosFlashCliArgs, UnimplementedHardwareTarget
from target_t5 import (
    TUYA_T5_DEFAULT_USB_UART_PID,
    TUYA_T5_DEFAULT_USB_UART_VID,
    TuyaT5Target,
    build_t5_tos_flash_argv,
    is_t5_default_usb_uart,
    pick_t5_monitor_port,
    t5_default_usb_uart_meta,
)

TARGETS: Dict[str, Callable[[], HardwareTarget]] = {
    "tuya_t5": TuyaT5Target,
    "t5": TuyaT5Target,
}


def get_target(name: str) -> HardwareTarget:
    key = name.strip().lower()
    if key not in TARGETS:
        raise ValueError(f"Unknown target {name!r}. Known: {sorted(TARGETS.keys())}")
    return TARGETS[key]()


def enumerate_ports() -> List[PortInfo]:
    if list_ports is None:
        return []
    out: List[PortInfo] = []
    for lp in list_ports.comports():
        out.append(
            PortInfo(
                device=lp.device,
                vid=lp.vid,
                pid=lp.pid,
                serial_number=lp.serial_number or None,
                manufacturer=lp.manufacturer or None,
                product=lp.product or None,
                description=lp.description or None,
            )
        )
    return out


def resolve_monitor_port(
    target: HardwareTarget,
    verbose: bool,
    allow_any_serial: bool,
) -> Tuple[Optional[PortInfo], List[PortInfo], List[str], str]:
    """
    Find the serial port for monitor/logging. Delegates to target.pick_default_monitor_port().

    Returns (chosen_port or None, all_enumerated_ports, diagnostic_lines, fail_reason_code).
    fail_reason_code is "" on success; otherwise e.g. pyserial_missing, no_serial_ports,
    t5_default_uart_not_found.
    """
    lines: List[str] = []
    if list_ports is None:
        msg = "pyserial is not installed; install with: pip install pyserial"
        lines.append(msg)
        _vlog(verbose, msg)
        return None, [], lines, "pyserial_missing"

    all_ports = enumerate_ports()
    lines.append(f"Enumerated {len(all_ports)} serial port(s).")
    _vlog(verbose, lines[-1])

    for p in sorted(all_ports, key=lambda x: x.device):
        if p.vid is not None and p.pid is not None:
            vidpid = f"VID 0x{p.vid:04x} PID 0x{p.pid:04x}"
        else:
            vidpid = "VID/PID unknown"
        prod = (p.product or p.description or "").strip() or "—"
        line = f"  {p.device}: {vidpid} | {prod}"
        lines.append(line)
        _vlog(verbose, line)

    if not all_ports:
        msg = "device not found: no serial/COM ports detected on this system."
        lines.append(msg)
        _vlog(verbose, msg)
        return None, [], lines, "no_serial_ports"

    chosen, fail_code = target.pick_default_monitor_port(
        all_ports, allow_any_serial, verbose, _vlog, lines
    )
    return chosen, all_ports, lines, fail_code


def _session_path() -> Path:
    return _repo_root() / ".target_logging" / "session.json"


def sanitize_log_name_suffix(raw: Optional[str], max_len: int = 96) -> str:
    """
    Turn free-text (e.g. AI description of what changed) into one safe filename segment.

    Strips control/path characters; collapses whitespace to underscores; caps length.
    Returns "" if nothing usable remains (caller falls back to timestamp-only name).
    """
    if not raw:
        return ""
    s = raw.strip()
    if not s:
        return ""
    s = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "", s)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s).strip("._-")
    if not s:
        return ""
    if len(s) > max_len:
        s = s[:max_len].rstrip("._-")
    return s


def _unique_log_file(day_dir: Path, ts: str, suffix: str) -> Path:
    """Build <ts>[_<suffix>][_<n>].log under day_dir without clobbering existing files."""
    if suffix:
        stem = f"{ts}_{suffix}"
    else:
        stem = ts
    p = day_dir / f"{stem}.log"
    n = 0
    while p.exists():
        n += 1
        p = day_dir / f"{stem}_{n}.log"
    return p


def _ensure_log_path(name_suffix: str = "") -> Tuple[Path, Path, str]:
    """
    Return (day_dir, log_file path, sanitized_suffix).

    name_suffix is optional free text (e.g. AI note); embedded in the filename after the timestamp.
    """
    root = _repo_root() / ".target_logging"
    day = datetime.now().strftime("%Y-%m-%d")
    day_dir = root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_suffix = sanitize_log_name_suffix(name_suffix) if name_suffix else ""
    log_file = _unique_log_file(day_dir, ts, safe_suffix)
    return day_dir, log_file, safe_suffix


def _log_suffix_meta(safe_applied: str, raw_request: str) -> Dict[str, Any]:
    """Optional JSON fields for AI: human note + sanitized segment used in the log filename."""
    out: Dict[str, Any] = {}
    raw = (raw_request or "").strip()
    if raw:
        out["log_suffix_note"] = raw[:240]
    if safe_applied:
        out["log_name_suffix"] = safe_applied
    return out


def _target_logging_root() -> Path:
    return _repo_root() / ".target_logging"


def find_latest_log_file() -> Optional[Path]:
    """Newest *.log under <repo>/.target_logging/ by modification time."""
    root = _target_logging_root()
    if not root.is_dir():
        return None
    newest: Optional[Path] = None
    newest_mtime = 0.0
    for p in root.rglob("*.log"):
        if not p.is_file():
            continue
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m >= newest_mtime:
            newest_mtime = m
            newest = p
    return newest


def write_latest_pointer(log_file: Path) -> None:
    """Write .target_logging/LATEST_LOG for agents (single line path)."""
    p = _target_logging_root() / "LATEST_LOG"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(log_file.resolve()) + "\n", encoding="utf-8")


# Short messages for AI assistants (show to user when hardware/session is missing).
AGENT_HINTS: Dict[str, str] = {
    "no_serial_ports": (
        "Tuya T5 target does not appear connected: no USB serial (CDC) devices were detected. "
        "Use a data-capable USB cable, try another port, reinstall the USB–UART driver if needed, "
        "and on Linux run: sudo usermod -aG dialout $USER (then log out and back in)."
    ),
    "t5_default_uart_not_found": (
        "USB serial port(s) exist, but none match the T5 onboard bridge (VID 0x1a86, PID 0x55d2). "
        "Connect the T5 dev board, or pass --allow-any-serial only for non-standard adapters."
    ),
    "pyserial_missing": (
        "Install pyserial: pip install -r .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool_requirements.txt"
    ),
    "no_active_session": (
        "No background logging session is running, so UART CLI and log tail are unavailable. "
        "Connect the T5 board, verify with list-devices, then run: service start --detach or debug-session run."
    ),
    "no_logging_session": (
        "No logging service was active; nothing to stop. Connect hardware and start a session first if you need serial logs."
    ),
    "control_channel_error": (
        "Could not talk to the logging service (it may have exited or the serial port was lost). "
        "Reconnect the board and start again: service start --detach or debug-session run."
    ),
    "control_server_timeout": (
        "Logging service did not become ready in time. Check USB connection and that no other app holds the serial port."
    ),
    "session_not_ready_after_start": (
        "Logging subprocess started but the control channel did not come up. Retry after reconnecting USB or rebooting the board."
    ),
    "no_log_files": (
        "No *.log files under .target_logging/ yet. Connect the device and run service start --detach or debug-session run to capture logs."
    ),
    "tos_py_not_found": (
        "tos.py was not found; run this tool from inside the TuyaOpen repository clone."
    ),
    "tos_env_incomplete": (
        "The TuyaOpen Python environment is not active or dependencies are missing. "
        "Follow skill tuyaopen-env-setup: source export.sh (or your venv), then retry. "
        "Typical fix: install SDK deps so tos.py can import its modules."
    ),
    "tos_failed": (
        "tos.py exited with an error. For flash/monitor, output was streamed above (stderr_tail may be empty). "
        "Confirm --project-dir points to an app with app_default.config; see skill tuyaopen-env-setup if imports fail."
    ),
    "serial_open_failed": (
        "Could not open the serial port. Close other serial monitors (screen, minicom, another IDE), "
        "unplug/replug USB, or on Linux ensure your user is in group dialout and no other process holds the port."
    ),
    "rpc_error": (
        "The logging service rejected this control request. Try service ping; if it fails, restart with "
        "service stop then service start --detach or debug-session run."
    ),
    "empty_response": (
        "No reply from the logging control channel (connection closed or service exiting). "
        "Reconnect USB and start a new logging session."
    ),
    "serial_not_open": (
        "The logger has no open serial port (service may be stopping or crashed). "
        "Run service stop, then service start --detach again."
    ),
}


def agent_hint_for(reason_code: str, fallback: str) -> str:
    return AGENT_HINTS.get(reason_code, fallback)


def agent_error(
    *,
    error: str,
    error_code: str,
    agent_hint: str,
    **extra: Any,
) -> Dict[str, Any]:
    """Standard JSON error object for AI agents (stable keys)."""
    payload: Dict[str, Any] = {
        "ok": False,
        "error": error,
        "error_code": error_code,
        "agent_hint": agent_hint,
    }
    payload.update(extra)
    return payload


def enrich_rpc_result(r: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure failed control-RPC payloads include error_code and agent_hint for agents."""
    if r.get("ok"):
        return r
    err_raw = r.get("error", "rpc_error")
    es = str(err_raw) if err_raw is not None else "rpc_error"
    if es == "empty_response":
        error_code = "empty_response"
    elif es == "serial_not_open":
        error_code = "serial_not_open"
    elif es in ("invalid_signal", "hw_reset_failed"):
        error_code = es
    elif es.startswith("unknown_op"):
        error_code = "unknown_op"
    else:
        error_code = "rpc_error"
    if error_code == "unknown_op":
        hint = agent_hint_for(
            "unknown_op",
            "Unknown control operation. Use ping, tail, cli_send, hw_reset, or stop.",
        )
    else:
        hint = agent_hint_for(error_code, agent_hint_for("rpc_error", es))
    out = dict(r)
    if "error_code" not in out:
        out["error_code"] = error_code
    if "agent_hint" not in out:
        out["agent_hint"] = hint
    return out


def agent_error_serial_open(exc: BaseException, port: str) -> Dict[str, Any]:
    """JSON error when pyserial cannot open the device."""
    detail = str(exc)
    hint = agent_hint_for(
        "serial_open_failed",
        f"Could not open {port}: {detail}",
    )
    return agent_error(
        error="serial_open_failed",
        error_code="serial_open_failed",
        agent_hint=hint,
        detail=detail,
        port=port,
    )


def device_not_found_payload(
    reason: str,
    diagnostic_lines: List[str],
    ports: List[PortInfo],
    as_json: bool,
    reason_code: str = "device_not_found",
    expected_usb_uart: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Structured error for agents (stdout JSON when --json)."""
    hint = agent_hint_for(reason_code, reason)
    payload: Dict[str, Any] = {
        "ok": False,
        "error": "device_not_found",
        "error_code": reason_code,
        "reason_code": reason_code,
        "reason": reason,
        "agent_hint": hint,
        "hardware_connected": False,
        "t5_target_connected": False,
        "discovery_log": diagnostic_lines,
        "ports_scanned": [p.to_dict() for p in ports],
    }
    if expected_usb_uart is not None:
        payload["expected_usb_uart"] = expected_usb_uart
        payload["expected_t5_usb_uart"] = expected_usb_uart
    if not as_json:
        for ln in diagnostic_lines:
            print(ln, file=sys.stderr)
        print(
            f"[agent_target_tool] ERROR: {reason}",
            file=sys.stderr,
            flush=True,
        )
        print(f"[agent_target_tool] {hint}", file=sys.stderr, flush=True)
    return payload


# ---------------------------------------------------------------------------
# Ring buffer for agent tail (thread-safe)
# ---------------------------------------------------------------------------
class RingBuffer:
    def __init__(self, max_bytes: int = 262144) -> None:
        self._max = max_bytes
        self._buf = bytearray()
        self._lock = threading.Lock()

    def append(self, data: bytes) -> None:
        with self._lock:
            self._buf.extend(data)
            if len(self._buf) > self._max:
                del self._buf[: len(self._buf) - self._max]

    def tail_bytes(self, n: int) -> bytes:
        with self._lock:
            if n <= 0 or not self._buf:
                return b""
            return bytes(self._buf[-n:])

    def tail_lines(self, n: int) -> str:
        raw = self.tail_bytes(self._max)
        if not raw:
            return ""
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if n <= 0:
            return text
        return "\n".join(lines[-n:])


# ---------------------------------------------------------------------------
# Serial service (background log + CLI inject)
# ---------------------------------------------------------------------------
DEFAULT_CTRL_HOST = "127.0.0.1"
DEFAULT_CTRL_PORT = 58761


@dataclass
class ServiceState:
    target: str = "tuya_t5"
    serial_port: str = ""
    baud: int = 460800
    log_file: str = ""
    control_host: str = DEFAULT_CTRL_HOST
    control_port: int = DEFAULT_CTRL_PORT
    pid: int = 0
    started_utc: str = ""
    timeout_sec: float = 0.0
    log_name_suffix: str = ""
    log_suffix_note: str = ""


class SerialSessionService:
    """
    Holds one serial port, a logging thread, and a small TCP control server.
    """

    def __init__(
        self,
        port: str,
        baud: int,
        log_path: Path,
        target: HardwareTarget,
        control_host: str = DEFAULT_CTRL_HOST,
        control_port: int = DEFAULT_CTRL_PORT,
        duration_sec: float = 0.0,
    ) -> None:
        self.port = port
        self.baud = baud
        self.log_path = log_path
        self.target = target
        self.ring = RingBuffer()
        self._ser: Any = None
        self._stop = threading.Event()
        self._log_fp: Optional[Any] = None
        self._reader_done = threading.Event()
        self._cli_active = False
        self._serial_lock = threading.Lock()
        self._control_host = control_host
        self._control_port = control_port
        self._srv: Optional[socket.socket] = None
        self._duration_sec = duration_sec
        self._start_mono = time.monotonic()

    def _open_serial(self) -> None:
        if serial is None:
            raise RuntimeError("pyserial is not installed. pip install pyserial")
        self._ser = serial.Serial(
            self.port,
            self.baud,
            timeout=0.05,
            write_timeout=2.0,
        )

    def _reader_loop(self) -> None:
        assert self._ser is not None
        while not self._stop.is_set():
            if self._duration_sec > 0 and (time.monotonic() - self._start_mono) >= self._duration_sec:
                self._stop.set()
                break
            try:
                if self._cli_active:
                    time.sleep(0.02)
                    continue
                with self._serial_lock:
                    waiting = getattr(self._ser, "in_waiting", 0) or 0
                    to_read = max(1, int(waiting))
                    chunk = self._ser.read(to_read)
                if chunk:
                    self.log_path.parent.mkdir(parents=True, exist_ok=True)
                    if self._log_fp is None:
                        self._log_fp = open(self.log_path, "ab", buffering=0)
                    self._log_fp.write(chunk)
                    self.ring.append(chunk)
            except Exception as exc:  # noqa: BLE001
                err = f"\n[agent_target_tool serial error] {exc}\n".encode("utf-8", errors="replace")
                self.ring.append(err)
                if self._log_fp:
                    self._log_fp.write(err)
                time.sleep(0.1)
        self._reader_done.set()

    def _handle_client(self, conn: socket.socket) -> None:
        f = conn.makefile("rwb", buffering=0)

        def read_line() -> Optional[str]:
            buf = bytearray()
            while not self._stop.is_set():
                try:
                    ch = f.read(1)
                    if not ch:
                        return None
                    if ch in (b"\n",):
                        try:
                            return buf.decode("utf-8").strip()
                        except Exception:
                            return None
                    buf.extend(ch)
                    if len(buf) > 65536:
                        return None
                except Exception:
                    return None
            return None

        while not self._stop.is_set():
            line = read_line()
            if line is None:
                break
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                reply = {"ok": False, "error": "invalid_json"}
                f.write((json.dumps(reply) + "\n").encode("utf-8"))
                continue
            op = msg.get("op")
            reply: Dict[str, Any] = {"ok": True}
            if op == "ping":
                reply["message"] = "pong"
            elif op == "status":
                reply["port"] = self.port
                reply["baud"] = self.baud
                reply["log_file"] = str(self.log_path)
                reply["target"] = self.target.name
            elif op == "tail":
                kind = msg.get("kind", "lines")
                if kind == "bytes":
                    reply["data_b64"] = ""  # optional: avoid huge payloads; use lines
                    reply["text"] = self.ring.tail_bytes(int(msg.get("n", 4096))).decode(
                        "utf-8", errors="replace"
                    )
                else:
                    reply["text"] = self.ring.tail_lines(int(msg.get("n", 100)))
            elif op == "cli_send":
                line_txt = msg.get("line", "")
                timeout = float(msg.get("timeout", 5.0))
                prompt = msg.get("prompt")
                reply.update(self._cli_send(line_txt, timeout=timeout, prompt_regex=prompt))
            elif op == "hw_reset":
                sig = str(msg.get("signal", "dtr")).lower()
                reply.update(self._hw_reset_signal(sig))
            elif op == "stop":
                self._stop.set()
                reply["message"] = "stopping"
            else:
                reply = {"ok": False, "error": f"unknown_op {op}"}
            f.write((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
        try:
            conn.close()
        except Exception:
            pass

    def _cli_send(
        self,
        line: str,
        timeout: float = 5.0,
        prompt_regex: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self._ser is None:
            return {"ok": False, "error": "serial_not_open"}
        out = bytearray()
        end = time.monotonic() + timeout
        pat = re.compile(prompt_regex) if prompt_regex else re.compile(r"tuya\s*>|#\s*$")
        with self._serial_lock:
            self._cli_active = True
            try:
                self._ser.reset_input_buffer()
                data = (line.rstrip() + "\r\n").encode("utf-8", errors="replace")
                self._ser.write(data)
                self._ser.flush()
                while time.monotonic() < end:
                    chunk = self._ser.read(4096)
                    if chunk:
                        out.extend(chunk)
                        self.ring.append(chunk)
                        if self._log_fp:
                            self._log_fp.write(chunk)
                        text = out.decode("utf-8", errors="replace")
                        if pat.search(text):
                            break
                    else:
                        time.sleep(0.02)
            finally:
                self._cli_active = False
        text = out.decode("utf-8", errors="replace")
        return {"ok": True, "response": text}

    def _hw_reset_signal(self, signal_name: str) -> Dict[str, Any]:
        """
        Pulse DTR and/or RTS to reset boards wired to USB-UART reset lines.
        Not all adapters expose these; may no-op or error on some ttyACM devices.
        """
        if self._ser is None:
            return {"ok": False, "error": "serial_not_open"}
        if signal_name not in ("dtr", "rts", "both"):
            return {"ok": False, "error": "invalid_signal", "detail": "use dtr, rts, or both"}
        with self._serial_lock:
            self._cli_active = True
            try:
                self._ser.reset_input_buffer()
                if signal_name in ("dtr", "both"):
                    self._ser.dtr = False
                if signal_name in ("rts", "both"):
                    self._ser.rts = False
                time.sleep(0.2)
                if signal_name in ("dtr", "both"):
                    self._ser.dtr = True
                if signal_name in ("rts", "both"):
                    self._ser.rts = True
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": "hw_reset_failed", "detail": str(exc)}
            finally:
                self._cli_active = False
        return {"ok": True, "method": f"hw_pulse_{signal_name}"}

    def _serve_loop(self) -> None:
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((self._control_host, self._control_port))
        self._srv.listen(2)
        self._srv.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
                conn.settimeout(120.0)
                t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break
        try:
            self._srv.close()
        except Exception:
            pass

    def run_foreground(self, serial_preopened: bool = False) -> None:
        if not serial_preopened:
            self._open_serial()
        t_reader = threading.Thread(target=self._reader_loop, daemon=True)
        t_reader.start()
        t_srv = threading.Thread(target=self._serve_loop, daemon=True)
        t_srv.start()
        try:
            while not self._stop.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            self._stop.set()
        self._stop.set()
        t_reader.join(timeout=2.0)
        if self._log_fp:
            try:
                self._log_fp.close()
            except Exception:
                pass
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass

    @staticmethod
    def client_rpc(
        host: str,
        port: int,
        payload: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.sendall(data)
            f = s.makefile("rwb", buffering=0)
            line = f.readline()
            if not line:
                return {"ok": False, "error": "empty_response"}
            return json.loads(line.decode("utf-8"))


def _write_session(st: ServiceState) -> None:
    p = _session_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "target": st.target,
        "serial_port": st.serial_port,
        "baud": st.baud,
        "log_file": st.log_file,
        "control_host": st.control_host,
        "control_port": st.control_port,
        "pid": st.pid,
        "started_utc": st.started_utc,
        "timeout_sec": st.timeout_sec,
    }
    if (st.log_name_suffix or "").strip():
        payload["log_name_suffix"] = st.log_name_suffix
    if (st.log_suffix_note or "").strip():
        payload["log_suffix_note"] = st.log_suffix_note
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_session() -> Optional[Dict[str, Any]]:
    p = _session_path()
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _clear_session() -> None:
    p = _session_path()
    if p.is_file():
        p.unlink()


def _pid_is_running(pid: int) -> bool:
    """Best-effort: True if process pid exists (Unix: kill 0)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def cleanup_stale_session_file() -> None:
    """Remove session.json if missing/invalid PID or process is not running."""
    sess = _read_session()
    if not sess:
        return
    pid_raw = sess.get("pid")
    if pid_raw is None:
        _clear_session()
        return
    try:
        pid = int(pid_raw)
    except (TypeError, ValueError):
        _clear_session()
        return
    if not _pid_is_running(pid):
        _clear_session()


def replace_previous_logging_session(as_json: bool, verbose: bool) -> bool:
    """
    Enforce a single logging service: drop stale session files, stop any live prior service.

    Returns True if a previous session was stopped (replaced).
    """
    cleanup_stale_session_file()
    if not _read_session():
        return False
    _vlog(verbose, "Single-instance policy: stopping existing logging service before starting a new one.")
    stop_existing_session(as_json)
    return True


def cmd_service_start(
    port: str,
    target_name: str,
    baud: int,
    as_json: bool,
    control_port: int,
    duration: float,
    detach: bool,
    verbose: bool,
    allow_any_serial: bool,
    log_suffix: str = "",
) -> Tuple[int, bool]:
    tgt = get_target(target_name)
    if baud <= 0:
        baud = tgt.monitor_baud()
    if not (port or "").strip():
        chosen, all_ports, lines, fail_code = resolve_monitor_port(
            tgt, verbose, allow_any_serial
        )
        if chosen is None:
            reason = (
                "Could not resolve a serial port. Connect the T5 board (USB–UART VID 0x1a86, PID 0x55d2) "
                "or pass --port explicitly; use --allow-any-serial only for non-standard bridges."
            )
            if fail_code == "pyserial_missing":
                reason = "pyserial is not installed; run: pip install pyserial"
            elif fail_code == "no_serial_ports":
                reason = "No serial/COM devices found; check USB cable, driver, and permissions (e.g. Linux dialout)."
            elif fail_code == "t5_default_uart_not_found":
                reason = (
                    "device not found: no interface with VID 0x1a86 and PID 0x55d2 "
                    "(T5 default WCH dual-serial). Other serial ports were listed in discovery_log."
                )
            pl = device_not_found_payload(
                reason,
                lines,
                all_ports,
                as_json,
                reason_code=fail_code or "device_not_found",
                expected_usb_uart=tgt.expected_usb_uart_meta(),
            )
            _out(pl, as_json)
            return 1, False
        port = chosen.device
    replaced = replace_previous_logging_session(as_json, verbose)
    _, log_file, safe_name_suffix = _ensure_log_path(log_suffix)
    write_latest_pointer(log_file)
    suffix_meta = _log_suffix_meta(safe_name_suffix, log_suffix)
    note_240 = (log_suffix or "").strip()[:240]
    st = ServiceState(
        target=target_name,
        serial_port=port,
        baud=baud,
        log_file=str(log_file),
        control_host=DEFAULT_CTRL_HOST,
        control_port=control_port,
        pid=os.getpid(),
        started_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        timeout_sec=duration,
        log_name_suffix=safe_name_suffix,
        log_suffix_note=note_240,
    )

    if detach:
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--target",
            target_name,
            "service",
            "run",
            "--port",
            port,
            "--baud",
            str(baud),
            "--log-file",
            str(log_file),
            "--control-port",
            str(control_port),
        ]
        if duration > 0:
            cmd.extend(["--duration", str(duration)])
        if safe_name_suffix:
            cmd.extend(["--log-name-suffix", safe_name_suffix])
        if note_240:
            cmd.extend(["--log-suffix-note", note_240])
        creationflags = 0
        preexec_fn = None
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            preexec_fn = os.setsid  # type: ignore[assignment]
        env_child = {**os.environ, "AGENT_TARGET_TOOL_JSON": "1" if as_json else "0"}
        subprocess.Popen(
            cmd,
            cwd=str(_repo_root()),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            preexec_fn=preexec_fn,
            env=env_child,
        )
        time.sleep(0.4)
        sess = _read_session()
        if sess and sess.get("pid"):
            _out(
                {
                    "ok": True,
                    "message": "detached_service_started",
                    "session": sess,
                    "log_file": str(log_file),
                    "replaced_previous_session": replaced,
                    **suffix_meta,
                },
                as_json,
            )
            return 0, replaced
        _out(
            {
                "ok": True,
                "message": "detached_started_check_session",
                "log_file": str(log_file),
                "control": {"host": DEFAULT_CTRL_HOST, "port": control_port},
                "replaced_previous_session": replaced,
                **suffix_meta,
            },
            as_json,
        )
        return 0, replaced

    svc = SerialSessionService(
        port=port,
        baud=baud,
        log_path=log_file,
        target=tgt,
        control_port=control_port,
        duration_sec=duration,
    )
    try:
        svc._open_serial()
    except BaseException as exc:
        _out(agent_error_serial_open(exc, port), as_json)
        return 1, replaced
    st.pid = os.getpid()
    _write_session(st)
    _out(
        {
            "ok": True,
            "message": "service_running_foreground",
            "replaced_previous_session": replaced,
            "session": {
                "serial_port": port,
                "baud": baud,
                "log_file": str(log_file),
                "control_host": DEFAULT_CTRL_HOST,
                "control_port": control_port,
                "pid": st.pid,
            },
            **suffix_meta,
        },
        as_json,
    )
    try:
        svc.run_foreground(serial_preopened=True)
    except BaseException as exc:
        _out(agent_error_serial_open(exc, port), as_json)
        return 1, replaced
    finally:
        _clear_session()
    return 0, replaced


def cmd_service_run(
    port: str,
    target_name: str,
    baud: int,
    log_file: Path,
    control_port: int,
    duration: float,
    log_name_suffix: str = "",
    log_suffix_note: str = "",
) -> int:
    """Internal: detached worker."""
    tgt = get_target(target_name)
    if baud <= 0:
        baud = tgt.monitor_baud()
    note_store = (log_suffix_note or "").strip()[:240]
    svc = SerialSessionService(
        port=port,
        baud=baud,
        log_path=log_file,
        target=tgt,
        control_port=control_port,
        duration_sec=duration,
    )
    try:
        svc._open_serial()
    except BaseException as exc:
        if os.environ.get("AGENT_TARGET_TOOL_JSON") == "1":
            print(json.dumps(agent_error_serial_open(exc, port)), flush=True)
        else:
            print(
                f"[agent_target_tool] serial open failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
        return 1
    st = ServiceState(
        target=target_name,
        serial_port=port,
        baud=baud,
        log_file=str(log_file),
        control_host=DEFAULT_CTRL_HOST,
        control_port=control_port,
        pid=os.getpid(),
        started_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        timeout_sec=duration,
        log_name_suffix=log_name_suffix or "",
        log_suffix_note=note_store,
    )
    _write_session(st)

    def _on_term(*_a: Any) -> None:
        svc._stop.set()

    signal.signal(signal.SIGINT, _on_term)
    signal.signal(signal.SIGTERM, _on_term)
    try:
        svc.run_foreground(serial_preopened=True)
    finally:
        _clear_session()
    return 0


def cmd_client_op(as_json: bool, payload: Dict[str, Any]) -> int:
    sess = _read_session()
    if not sess:
        hint = agent_hint_for(
            "no_active_session",
            "Start a logging session first (service start --detach or debug-session run).",
        )
        _out(
            agent_error(
                error="no_active_session",
                error_code="no_active_session",
                agent_hint=hint,
                logging_service_active=False,
            ),
            as_json,
        )
        return 1
    host = sess.get("control_host", DEFAULT_CTRL_HOST)
    port = int(sess.get("control_port", DEFAULT_CTRL_PORT))
    try:
        r = enrich_rpc_result(SerialSessionService.client_rpc(host, port, payload))
    except Exception as exc:  # noqa: BLE001
        hint = agent_hint_for("control_channel_error", str(exc))
        _out(
            agent_error(
                error="control_channel_error",
                error_code="control_channel_error",
                agent_hint=hint,
                detail=str(exc),
                logging_service_active=True,
            ),
            as_json,
        )
        return 1
    _out(r, as_json)
    return 0 if r.get("ok") else 1


def stop_existing_session(as_json: bool) -> int:
    """Stop detached/foreground service: control RPC then best-effort PID kill."""
    sess_before = _read_session()
    if not sess_before:
        return 0
    pid = int(sess_before["pid"]) if sess_before.get("pid") else None
    r: Dict[str, Any] = {"ok": True, "message": "stopping"}
    try:
        host = sess_before.get("control_host", DEFAULT_CTRL_HOST)
        cport = int(sess_before.get("control_port", DEFAULT_CTRL_PORT))
        r = SerialSessionService.client_rpc(host, cport, {"op": "stop"}, timeout=10.0)
    except Exception as exc:  # noqa: BLE001
        r = {"ok": False, "error": str(exc)}
    if pid is not None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                )
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    time.sleep(0.3)
    _clear_session()
    if not as_json:
        print("Stopped previous logging session.", file=sys.stderr)
    return 0 if r.get("ok", True) else 1


def cmd_debug_session_run(
    port: str,
    target_name: str,
    baud: int,
    as_json: bool,
    control_port: int,
    duration: float,
    verbose: bool,
    allow_any_serial: bool,
    boot_wait: float,
    hw_reset: bool,
    cli_reboot: bool,
    reboot_line: str,
    hw_signal: str,
    log_suffix: str = "",
) -> int:
    """
    Start detached logging, reset target (hardware pulse and/or CLI reboot), wait for boot noise.
    Prior session is always stopped (single-instance policy); see cmd_service_start.
    """
    rc, replaced_svc = cmd_service_start(
        port=port,
        target_name=target_name,
        baud=baud,
        as_json=as_json,
        control_port=control_port,
        duration=duration,
        detach=True,
        verbose=verbose,
        allow_any_serial=allow_any_serial,
        log_suffix=log_suffix,
    )
    if rc != 0:
        return rc

    sess = _read_session()
    if not sess or not sess.get("control_port"):
        hint = agent_hint_for(
            "session_not_ready_after_start",
            "Detached service did not publish a valid session file.",
        )
        _out(
            agent_error(
                error="session_not_ready_after_start",
                error_code="session_not_ready_after_start",
                agent_hint=hint,
            ),
            as_json,
        )
        return 1

    host = sess.get("control_host", DEFAULT_CTRL_HOST)
    cport = int(sess.get("control_port", DEFAULT_CTRL_PORT))
    log_path = sess.get("log_file", "")

    for _ in range(50):
        try:
            ping = SerialSessionService.client_rpc(host, cport, {"op": "ping"}, timeout=2.0)
            if ping.get("ok"):
                break
        except Exception:
            pass
        time.sleep(0.1)
    else:
        hint = agent_hint_for(
            "control_server_timeout",
            "Control server did not respond to ping in time.",
        )
        _out(
            agent_error(
                error="control_server_timeout",
                error_code="control_server_timeout",
                agent_hint=hint,
                log_file=log_path,
            ),
            as_json,
        )
        return 1

    steps: List[Dict[str, Any]] = []
    if hw_reset:
        hr = SerialSessionService.client_rpc(
            host, cport, {"op": "hw_reset", "signal": hw_signal}, timeout=15.0
        )
        steps.append({"step": "hw_reset", "signal": hw_signal, "result": hr})
    elif cli_reboot:
        cr = SerialSessionService.client_rpc(
            host,
            cport,
            {
                "op": "cli_send",
                "line": reboot_line,
                "timeout": 8.0,
                "prompt": None,
            },
            timeout=30.0,
        )
        steps.append({"step": "cli_reboot", "line": reboot_line, "result": cr})

    if boot_wait > 0:
        time.sleep(boot_wait)

    sess2 = _read_session() or sess
    dbg_meta = _log_suffix_meta(sanitize_log_name_suffix(log_suffix), log_suffix)
    _out(
        {
            "ok": True,
            "message": "debug_session_ready",
            "log_file": log_path,
            "session": sess2,
            "replaced_previous_session": replaced_svc,
            "steps": steps,
            "next": {
                "tail": "service tail -n 200",
                "cli": "cli help | cli send --line \"…\"",
                "stop": "service stop",
            },
            **dbg_meta,
        },
        as_json,
    )
    return 0


def cmd_logs_latest(as_json: bool) -> int:
    """Print path to newest .target_logging/**/*.log (and LATEST_LOG if present)."""
    root = _target_logging_root()
    ptr = root / "LATEST_LOG"
    ptr_path: Optional[str] = None
    if ptr.is_file():
        try:
            ptr_path = ptr.read_text(encoding="utf-8").strip()
        except OSError:
            ptr_path = None
    latest = find_latest_log_file()
    out: Dict[str, Any] = {
        "ok": True,
        "target_logging_dir": str(root),
        "latest_log_by_mtime": str(latest) if latest else None,
        "LATEST_LOG_pointer": ptr_path,
    }
    if ptr_path and Path(ptr_path).is_file():
        out["recommended"] = ptr_path
    elif latest:
        out["recommended"] = str(latest)
    else:
        out["recommended"] = None
        out["agent_hint"] = agent_hint_for(
            "no_log_files",
            "No capture files yet under .target_logging/.",
        )
    _out(out, as_json)
    if not as_json and out.get("recommended"):
        print(out["recommended"])
    return 0


def run_tos(
    args: List[str],
    project_dir: Path,
    as_json: bool,
) -> int:
    """
    Run tos.py flash or monitor. Child output streams to the terminal; with --json,
    only the final summary is JSON on stdout (scroll up for tyutool logs).
    """
    tos = _repo_root() / "tos.py"
    if not tos.is_file():
        hint = agent_hint_for("tos_py_not_found", f"Expected tos.py at {tos}")
        _out(
            agent_error(
                error="tos.py_not_found",
                error_code="tos_py_not_found",
                agent_hint=hint,
                path=str(tos),
            ),
            as_json,
        )
        return 1
    cmd = [sys.executable, str(tos)] + args
    # Inherit child stdout/stderr so tyutool progress is visible (capture hid output until exit).
    proc = subprocess.run(
        cmd,
        cwd=str(project_dir),
        env={**os.environ},
        stdin=subprocess.DEVNULL,
    )
    base: Dict[str, Any] = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "cmd": cmd,
        "streamed_to_terminal": True,
    }
    if proc.returncode != 0:
        base["error_code"] = "tos_failed"
        base["agent_hint"] = agent_hint_for(
            "tos_failed",
            "tos.py exited with an error — output was streamed above (not in JSON). "
            "If you saw ModuleNotFoundError, run: cd <repo> && . ./export.sh. "
            "Otherwise check USB, use flash -p / monitor -p, or bootloader timing.",
        )
    _out(base, as_json)
    return proc.returncode


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="TuyaOpen AI target helper (serial + tos.py wrappers).")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON on stdout")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print discovery steps to stderr (safe with --json; does not mix into stdout JSON).",
    )
    parser.add_argument(
        "--target",
        default="tuya_t5",
        help=f"Hardware target profile ({', '.join(sorted(TARGETS.keys()))})",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory containing app_default.config for tos.py flash/monitor (default: cwd)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-devices", help="List serial ports with USB metadata")
    p_list.set_defaults(handler="list_devices")

    p_pick = sub.add_parser("pick-port", help="Print best-guess port for --target (text or JSON)")
    p_pick.add_argument(
        "--allow-any-serial",
        action="store_true",
        help="If T5 default USB–UART (VID 0x1a86, PID 0x55d2) is absent, fall back to best heuristic port.",
    )
    p_pick.set_defaults(handler="pick_port")

    p_flash = sub.add_parser("flash", help="Run: tos.py flash (from --project-dir)")
    p_flash.add_argument("-p", "--port", default="", help="Serial port")
    p_flash.add_argument("-b", "--baud", type=int, default=0, help="Flash baud (0 = auto)")
    p_flash.add_argument("-d", "--debug", action="store_true", help="Flash debug")
    p_flash.set_defaults(handler="flash")

    p_mon = sub.add_parser("monitor", help="Run: tos.py monitor (foreground; blocks)")
    p_mon.add_argument("-p", "--port", default="", help="Serial port")
    p_mon.add_argument("-b", "--baud", type=int, default=0, help="Monitor baud (0 = auto)")
    p_mon.set_defaults(handler="monitor")

    p_ss = sub.add_parser("service", help="Background log + control channel")
    ss_sub = p_ss.add_subparsers(dest="svc_cmd", required=True)

    p_start = ss_sub.add_parser("start", help="Start logging + TCP control (foreground or --detach)")
    p_start.add_argument(
        "-p",
        "--port",
        default="",
        help="Serial port for monitor/log; omit to auto-detect T5 default USB–UART (VID 0x1a86, PID 0x55d2)",
    )
    p_start.add_argument(
        "--allow-any-serial",
        action="store_true",
        help="If T5 default USB–UART is absent, fall back to best heuristic port (not for production T5 boards).",
    )
    p_start.add_argument("-b", "--baud", type=int, default=0, help="Monitor baud (0 = target default)")
    p_start.add_argument(
        "--control-port",
        type=int,
        default=DEFAULT_CTRL_PORT,
        help=f"Local TCP port for control JSON (default {DEFAULT_CTRL_PORT})",
    )
    p_start.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Auto-stop after N seconds (0 = until stop/KILL)",
    )
    p_start.add_argument(
        "--detach",
        action="store_true",
        help="Spawn detached process (release calling terminal immediately)",
    )
    p_start.add_argument(
        "--log-suffix",
        default="",
        metavar="TEXT",
        help=(
            "Optional label embedded in the log filename after the timestamp "
            "(e.g. what changed or what this capture is for); sanitized for the filesystem."
        ),
    )
    p_start.set_defaults(handler="service_start")

    p_run = ss_sub.add_parser("run", help=argparse.SUPPRESS)
    p_run.add_argument("-p", "--port", required=True)
    p_run.add_argument("-b", "--baud", type=int, default=0)
    p_run.add_argument("--log-file", type=Path, required=True)
    p_run.add_argument("--control-port", type=int, default=DEFAULT_CTRL_PORT)
    p_run.add_argument("--duration", type=float, default=0.0)
    p_run.add_argument("--log-name-suffix", default="", help=argparse.SUPPRESS)
    p_run.add_argument("--log-suffix-note", default="", help=argparse.SUPPRESS)
    p_run.set_defaults(handler="service_run")

    p_tail = ss_sub.add_parser("tail", help="Tail buffered log via active session")
    p_tail.add_argument("-n", "--lines", type=int, default=100)
    p_tail.set_defaults(handler="service_tail")

    p_ping = ss_sub.add_parser("ping", help="Ping control server")
    p_ping.set_defaults(handler="service_ping")

    p_status = ss_sub.add_parser("status", help="Show active serial session (port, baud, log path)")
    p_status.set_defaults(handler="service_status")

    p_stop = ss_sub.add_parser("stop", help="Stop logging service (via control channel)")
    p_stop.set_defaults(handler="service_stop")

    p_cli = sub.add_parser("cli", help="Hardware UART CLI via active logging session")
    cli_sub = p_cli.add_subparsers(dest="cli_cmd", required=True)
    p_send = cli_sub.add_parser("send", help="Send a line (e.g. tal_cli / tuya> )")
    p_send.add_argument("--line", required=True, help="Command line to send")
    p_send.add_argument("--timeout", type=float, default=8.0)
    p_send.add_argument("--prompt", default=None, help="Optional regex for end of response")
    p_send.set_defaults(handler="cli_send")

    p_cli_help = cli_sub.add_parser("help", help="Send 'help' and capture response until prompt")
    p_cli_help.add_argument("--timeout", type=float, default=15.0)
    p_cli_help.add_argument("--prompt", default=None, help="Optional regex for prompt (default: tuya> / #)")
    p_cli_help.set_defaults(handler="cli_help")

    p_cli_reboot = cli_sub.add_parser(
        "reboot",
        help="Reboot target by sending a CLI line (default: reboot)",
    )
    p_cli_reboot.add_argument(
        "--line",
        default="reboot",
        help="CLI command (device may use reboot, reset, etc.)",
    )
    p_cli_reboot.add_argument("--timeout", type=float, default=8.0)
    p_cli_reboot.set_defaults(handler="cli_reboot")

    p_logs = sub.add_parser("logs", help="Query .target_logging under repo root")
    logs_sub = p_logs.add_subparsers(dest="logs_cmd", required=True)
    p_logs_latest = logs_sub.add_parser(
        "latest",
        help="Show newest *.log path (and LATEST_LOG pointer if set)",
    )
    p_logs_latest.set_defaults(handler="logs_latest")

    p_dbg = sub.add_parser(
        "debug-session",
        help="Full loop: start detached monitor → reset → boot wait → ready for tail/cli",
    )
    dbg_sub = p_dbg.add_subparsers(dest="dbg_cmd", required=True)
    p_dbg_run = dbg_sub.add_parser("run", help="Run one debug capture session")
    p_dbg_run.add_argument(
        "-p",
        "--port",
        default="",
        help="Monitor serial port; omit for T5 auto-detect",
    )
    p_dbg_run.add_argument(
        "--allow-any-serial",
        action="store_true",
        help="Allow non-T5 USB–UART when auto-picking port",
    )
    p_dbg_run.add_argument("-b", "--baud", type=int, default=0)
    p_dbg_run.add_argument("--control-port", type=int, default=DEFAULT_CTRL_PORT)
    p_dbg_run.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Auto-stop logging after N seconds (0 = until service stop)",
    )
    p_dbg_run.add_argument(
        "--boot-wait",
        type=float,
        default=4.0,
        help="Seconds to sleep after reset for boot logs to appear",
    )
    p_dbg_run.add_argument(
        "--hw-reset",
        action="store_true",
        help="Pulse DTR/RTS instead of CLI reboot (adapter must expose lines)",
    )
    p_dbg_run.add_argument(
        "--hw-signal",
        default="dtr",
        choices=["dtr", "rts", "both"],
        help="Which modem line to pulse for --hw-reset",
    )
    p_dbg_run.add_argument(
        "--no-cli-reboot",
        dest="cli_reboot",
        action="store_false",
        default=True,
        help="Do not send a CLI reboot line (default: send reboot; use with --hw-reset)",
    )
    p_dbg_run.add_argument(
        "--reboot-line",
        default="reboot",
        help="CLI line for soft reboot when CLI reboot is enabled",
    )
    p_dbg_run.add_argument(
        "--log-suffix",
        default="",
        metavar="TEXT",
        help="Same as service start --log-suffix: optional note in the log filename for this session.",
    )
    p_dbg_run.set_defaults(handler="debug_session_run")

    args = parser.parse_args()

    as_json: bool = args.json
    verbose: bool = args.verbose

    if args.handler == "list_devices":
        _vlog(verbose, "list-devices: scanning USB serial interfaces …")
        if list_ports is None:
            lines = ["pyserial is not installed; install with: pip install pyserial"]
            for ln in lines:
                _vlog(verbose, ln)
            hint = agent_hint_for("pyserial_missing", lines[0])
            _out(
                agent_error(
                    error="pyserial_missing",
                    error_code="pyserial_missing",
                    agent_hint=hint,
                    discovery_log=lines,
                    hardware_connected=False,
                    t5_target_connected=False,
                ),
                as_json,
            )
            return 1
        ports = enumerate_ports()
        tgt = get_target(args.target)
        if not ports:
            _, all_ports, lines, fail_code = resolve_monitor_port(tgt, verbose, False)
            pl = device_not_found_payload(
                "No USB serial devices detected; T5 hardware target does not appear connected.",
                lines,
                all_ports,
                as_json,
                reason_code=fail_code or "no_serial_ports",
                expected_usb_uart=tgt.expected_usb_uart_meta(),
            )
            _out(pl, as_json)
            return 1
        scored: List[Tuple[int, PortInfo]] = []
        for p in ports:
            scored.append((tgt.port_match_score(p) + (1 if p.vid else 0), p))
        scored.sort(key=lambda x: -x[0])
        port_rows: List[Dict[str, Any]] = []
        for _, p in scored:
            row = p.to_dict()
            row["t5_default_bridge"] = is_t5_default_usb_uart(p)
            port_rows.append(row)
        t5_connected = any(is_t5_default_usb_uart(p) for p in ports)
        if t5_connected:
            list_hint = (
                "T5 default USB–UART (VID 0x1a86, PID 0x55d2) detected. "
                "Use service start --detach or debug-session run to capture logs."
            )
        else:
            list_hint = agent_hint_for(
                "t5_default_uart_not_found",
                "No T5 onboard bridge found among enumerated ports.",
            )
        _vlog(verbose, f"list-devices: {len(port_rows)} port(s); T5 default bridge is VID 0x1a86 PID 0x55d2.")
        list_body: Dict[str, Any] = {
            "ok": True,
            "target": tgt.name,
            "default_monitor_baud": tgt.monitor_baud(),
            "ports": port_rows,
            "hardware_connected": True,
            "t5_target_connected": t5_connected,
            "agent_hint": list_hint,
        }
        exp_list = tgt.expected_usb_uart_meta()
        if exp_list is not None:
            list_body["expected_usb_uart"] = exp_list
            list_body["expected_t5_usb_uart"] = exp_list
        _out(list_body, as_json)
        return 0

    if args.handler == "pick_port":
        tgt = get_target(args.target)
        allow_any = getattr(args, "allow_any_serial", False)
        chosen, all_ports, lines, fail_code = resolve_monitor_port(tgt, verbose, allow_any)
        if chosen is None:
            reason = (
                "Could not pick a serial port. Connect the T5 (USB–UART VID 0x1a86, PID 0x55d2) "
                "or use --allow-any-serial / explicit --port on other commands."
            )
            if fail_code == "pyserial_missing":
                reason = "pyserial is not installed; run: pip install pyserial"
            elif fail_code == "no_serial_ports":
                reason = "No serial/COM devices found; check USB, driver, permissions."
            elif fail_code == "t5_default_uart_not_found":
                reason = (
                    "device not found: no USB interface with VID 0x1a86 and PID 0x55d2 "
                    "(T5 default WCH dual-serial)."
                )
            pl = device_not_found_payload(
                reason,
                lines,
                all_ports,
                as_json,
                reason_code=fail_code or "device_not_found",
                expected_usb_uart=tgt.expected_usb_uart_meta(),
            )
            _out(pl, as_json)
            return 1
        is_t5 = is_t5_default_usb_uart(chosen)
        exp_meta = tgt.expected_usb_uart_meta()
        out_obj: Dict[str, Any] = {
            "ok": True,
            "port": chosen.device,
            "hint": chosen.to_dict(),
            "hint_t5_default_bridge": is_t5,
            "hardware_connected": True,
            "t5_target_connected": is_t5,
            "default_monitor_baud": tgt.monitor_baud(),
            "agent_hint": (
                "Monitor port selected; start logging with service start --detach or debug-session run."
                if is_t5
                else agent_hint_for(
                    "t5_default_uart_not_found",
                    "Picked a non-T5 serial port (--allow-any-serial or heuristic).",
                )
            ),
        }
        if exp_meta is not None:
            out_obj["expected_usb_uart"] = exp_meta
            out_obj["expected_t5_usb_uart"] = exp_meta
        if verbose:
            out_obj["discovery_log"] = lines
        _out(out_obj, as_json)
        if not as_json:
            print(chosen.device)
        return 0

    if args.handler == "flash":
        tgt = get_target(getattr(args, "target", "tuya_t5"))
        flash_argv = tgt.build_tos_flash_argv(
            TosFlashCliArgs(
                port=getattr(args, "port", "") or "",
                baud=int(getattr(args, "baud", 0) or 0),
                debug=bool(getattr(args, "debug", False)),
            )
        )
        extra = ["flash"] + flash_argv
        return run_tos(extra, args.project_dir, as_json)

    if args.handler == "monitor":
        extra = ["monitor"]
        if args.port:
            extra.extend(["-p", args.port])
        if args.baud:
            extra.extend(["-b", str(args.baud)])
        return run_tos(extra, args.project_dir, as_json)

    if args.handler == "service_start":
        rc, _rep = cmd_service_start(
            port=args.port,
            target_name=args.target,
            baud=args.baud,
            as_json=as_json,
            control_port=args.control_port,
            duration=args.duration,
            detach=args.detach,
            verbose=verbose,
            allow_any_serial=getattr(args, "allow_any_serial", False),
            log_suffix=getattr(args, "log_suffix", ""),
        )
        return rc

    if args.handler == "service_run":
        return cmd_service_run(
            port=args.port,
            target_name=getattr(args, "target", "tuya_t5"),
            baud=args.baud,
            log_file=args.log_file,
            control_port=args.control_port,
            duration=args.duration,
            log_name_suffix=getattr(args, "log_name_suffix", ""),
            log_suffix_note=getattr(args, "log_suffix_note", ""),
        )

    if args.handler == "service_tail":
        return cmd_client_op(as_json, {"op": "tail", "n": args.lines})

    if args.handler == "service_ping":
        return cmd_client_op(as_json, {"op": "ping"})

    if args.handler == "service_status":
        return cmd_client_op(as_json, {"op": "status"})

    if args.handler == "service_stop":
        cleanup_stale_session_file()
        sess_before = _read_session()
        if not sess_before:
            _out(
                {
                    "ok": True,
                    "message": "no_logging_session",
                    "error_code": "no_logging_session",
                    "logging_service_active": False,
                    "agent_hint": agent_hint_for(
                        "no_logging_session",
                        "No background logger was running.",
                    ),
                },
                as_json,
            )
            return 0
        pid = int(sess_before["pid"]) if sess_before and sess_before.get("pid") else None
        rpc_ok = False
        rpc_detail: Optional[str] = None
        try:
            host = sess_before.get("control_host", DEFAULT_CTRL_HOST)
            cport = int(sess_before.get("control_port", DEFAULT_CTRL_PORT))
            rr = SerialSessionService.client_rpc(host, cport, {"op": "stop"}, timeout=10.0)
            rpc_ok = bool(rr.get("ok"))
            if not rpc_ok:
                rpc_detail = str(rr.get("error", rr))
        except Exception as exc:  # noqa: BLE001
            rpc_detail = str(exc)
        if pid is not None:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        capture_output=True,
                        text=True,
                    )
                else:
                    os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        _clear_session()
        body: Dict[str, Any] = {
            "ok": True,
            "message": "service_stopped",
            "logging_service_active": False,
            "control_stop_ok": rpc_ok,
        }
        if not rpc_ok:
            body["agent_hint"] = agent_hint_for(
                "control_channel_error",
                "Control RPC failed or was unreachable; session file cleared and PID signaled anyway.",
            )
            if rpc_detail:
                body["detail"] = rpc_detail
        _out(body, as_json)
        return 0

    if args.handler == "cli_send":
        return cmd_client_op(
            as_json,
            {
                "op": "cli_send",
                "line": args.line,
                "timeout": args.timeout,
                "prompt": args.prompt,
            },
        )

    if args.handler == "cli_help":
        return cmd_client_op(
            as_json,
            {
                "op": "cli_send",
                "line": "help",
                "timeout": args.timeout,
                "prompt": args.prompt,
            },
        )

    if args.handler == "cli_reboot":
        return cmd_client_op(
            as_json,
            {
                "op": "cli_send",
                "line": args.line,
                "timeout": args.timeout,
                "prompt": None,
            },
        )

    if args.handler == "logs_latest":
        return cmd_logs_latest(as_json)

    if args.handler == "debug_session_run":
        hr = getattr(args, "hw_reset", False)
        cli_rb = getattr(args, "cli_reboot", True) and not hr
        return cmd_debug_session_run(
            port=args.port,
            target_name=args.target,
            baud=args.baud,
            as_json=as_json,
            control_port=args.control_port,
            duration=args.duration,
            verbose=verbose,
            allow_any_serial=getattr(args, "allow_any_serial", False),
            boot_wait=float(getattr(args, "boot_wait", 4.0)),
            hw_reset=hr,
            cli_reboot=cli_rb,
            reboot_line=getattr(args, "reboot_line", "reboot"),
            hw_signal=getattr(args, "hw_signal", "dtr"),
            log_suffix=getattr(args, "log_suffix", ""),
        )

    parser.error("Unhandled command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
