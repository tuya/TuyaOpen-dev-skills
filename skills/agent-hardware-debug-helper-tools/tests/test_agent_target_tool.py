#!/usr/bin/env python3
# coding=utf-8
"""
Unit tests for agent_target_tool.py (no USB hardware required).

Run from TuyaOpen repo root:
  pip install -r .agents/skills/agent-hardware-debug-helper-tools/agent_target_tool_requirements.txt
  pytest -q .agents/skills/agent-hardware-debug-helper-tools/tests
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Load the script as a module (no package install)
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve().parent.parent / "agent_target_tool.py"


def _load_agent_target_tool() -> Any:
    """Load script as a module; must pre-register in sys.modules for @dataclass."""
    name = "agent_target_tool"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


att = _load_agent_target_tool()


def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p.parent, *p.parents]:
        if (parent / "tos.py").is_file():
            return parent
    pytest.fail("Could not find TuyaOpen repo root (tos.py); run tests inside the clone.")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
class TestEnrichRpcResult:
    def test_adds_hint_for_empty_response(self) -> None:
        r = att.enrich_rpc_result({"ok": False, "error": "empty_response"})
        assert r["error_code"] == "empty_response"
        assert "agent_hint" in r

    def test_unknown_op_prefix(self) -> None:
        r = att.enrich_rpc_result({"ok": False, "error": "unknown_op foo"})
        assert r["error_code"] == "unknown_op"


class TestSanitizeLogNameSuffix:
    def test_sanitizes_spaces_and_forbidden_chars(self) -> None:
        s = att.sanitize_log_name_suffix("fix: LED ripple  after flash")
        assert "/" not in s and ":" not in s
        assert "LED" in s or "led" in s.lower()
        assert "_" in s

    def test_empty_and_unusable(self) -> None:
        assert att.sanitize_log_name_suffix("") == ""
        assert att.sanitize_log_name_suffix("   ") == ""
        assert att.sanitize_log_name_suffix("///") == ""


class TestT5UsbIdentification:
    def test_is_t5_default_usb_uart_matches_vid_pid(self) -> None:
        p = att.PortInfo(device="/dev/ttyACM1", vid=0x1A86, pid=0x55D2)
        assert att.is_t5_default_usb_uart(p) is True

    def test_is_t5_default_usb_uart_rejects_other_bridge(self) -> None:
        p = att.PortInfo(device="/dev/ttyUSB0", vid=0x1A86, pid=0x7523)
        assert att.is_t5_default_usb_uart(p) is False

    def test_is_t5_default_usb_uart_requires_vid_pid(self) -> None:
        p = att.PortInfo(device="/dev/ttyACM0", vid=None, pid=None)
        assert att.is_t5_default_usb_uart(p) is False

    def test_t5_default_usb_uart_meta_shape(self) -> None:
        m = att.t5_default_usb_uart_meta()
        assert m["vid_int"] == att.TUYA_T5_DEFAULT_USB_UART_VID
        assert m["pid_int"] == att.TUYA_T5_DEFAULT_USB_UART_PID


class TestMonitorPortPick:
    def test_pick_t5_monitor_port_prefers_higher_tty_index(self) -> None:
        a = att.PortInfo(device="/dev/ttyACM0", vid=0x1A86, pid=0x55D2)
        b = att.PortInfo(device="/dev/ttyACM1", vid=0x1A86, pid=0x55D2)
        chosen = att.pick_t5_monitor_port([a, b])
        assert chosen is not None
        assert chosen.device == "/dev/ttyACM1"

    def test_pick_t5_monitor_port_empty(self) -> None:
        assert att.pick_t5_monitor_port([]) is None


class TestTosFlashCli:
    def test_build_argv_matches_tos_flash_flags(self) -> None:
        cli = att.TosFlashCliArgs(port="/dev/ttyACM0", baud=921600, debug=True)
        argv = att.TuyaT5Target().build_tos_flash_argv(cli)
        assert argv == ["-d", "-p", "/dev/ttyACM0", "-b", "921600"]

    def test_omits_flags_when_empty(self) -> None:
        assert att.TuyaT5Target().build_tos_flash_argv(att.TosFlashCliArgs()) == []

    def test_module_helper_matches_instance(self) -> None:
        cli = att.TosFlashCliArgs(port="/dev/ttyUSB0", baud=0, debug=False)
        assert att.build_t5_tos_flash_argv(cli) == att.TuyaT5Target().build_tos_flash_argv(cli)


class TestRepoRoot:
    def test_repo_root_contains_tos_py(self) -> None:
        root = att._repo_root()
        assert (root / "tos.py").is_file()


# ---------------------------------------------------------------------------
# Filesystem helpers (isolated with monkeypatch)
# ---------------------------------------------------------------------------
class TestTargetLoggingHelpers:
    @pytest.fixture
    def fake_repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        (tmp_path / "tos.py").write_text("# test stub\n", encoding="utf-8")
        (tmp_path / ".target_logging").mkdir()
        monkeypatch.setattr(att, "_repo_root", lambda: tmp_path)
        return tmp_path

    def test_find_latest_log_file_by_mtime(self, fake_repo: Path) -> None:
        day = fake_repo / ".target_logging" / "2099-01-01"
        day.mkdir(parents=True)
        older = day / "a.log"
        newer = day / "b.log"
        older.write_text("a", encoding="utf-8")
        newer.write_text("b", encoding="utf-8")
        import os

        st_a = older.stat()
        os.utime(older, (st_a.st_atime, st_a.st_mtime - 100))
        latest = att.find_latest_log_file()
        assert latest is not None
        assert latest.resolve() == newer.resolve()

    def test_write_latest_pointer(self, fake_repo: Path) -> None:
        logf = fake_repo / ".target_logging" / "x.log"
        logf.write_text("", encoding="utf-8")
        att.write_latest_pointer(logf)
        ptr = (fake_repo / ".target_logging" / "LATEST_LOG").read_text(encoding="utf-8").strip()
        assert Path(ptr) == logf.resolve()

    def test_cleanup_stale_session_removes_dead_pid(
        self, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sess = fake_repo / ".target_logging" / "session.json"
        sess.write_text(
            json.dumps({"pid": 999_001_999, "control_port": 58761}),
            encoding="utf-8",
        )

        def never_running(_pid: int) -> bool:
            return False

        monkeypatch.setattr(att, "_pid_is_running", never_running)
        att.cleanup_stale_session_file()
        assert not sess.is_file()

    def test_cleanup_stale_session_keeps_live_pid(
        self, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sess = fake_repo / ".target_logging" / "session.json"
        payload = {"pid": 42, "control_port": 58761}
        sess.write_text(json.dumps(payload), encoding="utf-8")

        def always_running(_pid: int) -> bool:
            return True

        monkeypatch.setattr(att, "_pid_is_running", always_running)
        att.cleanup_stale_session_file()
        assert sess.is_file()


class TestDeviceNotFoundPayload:
    def test_device_not_found_payload_keys(self) -> None:
        pl = att.device_not_found_payload(
            reason="test",
            diagnostic_lines=["line1"],
            ports=[],
            as_json=True,
            reason_code="t5_default_uart_not_found",
            expected_usb_uart=att.t5_default_usb_uart_meta(),
        )
        assert pl["ok"] is False
        assert pl["error"] == "device_not_found"
        assert pl["error_code"] == "t5_default_uart_not_found"
        assert pl["reason_code"] == "t5_default_uart_not_found"
        assert "expected_t5_usb_uart" in pl
        assert "agent_hint" in pl and pl["agent_hint"]
        assert pl["hardware_connected"] is False
        assert pl["t5_target_connected"] is False


# ---------------------------------------------------------------------------
# CLI smoke (subprocess, real repo)
# ---------------------------------------------------------------------------
class TestCliSmoke:
    def test_logs_latest_json_exit_zero(self) -> None:
        root = _find_repo_root()
        cmd = [
            sys.executable,
            str(_SCRIPT),
            "--json",
            "logs",
            "latest",
        ]
        r = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout.strip())
        assert data.get("ok") is True
        assert "target_logging_dir" in data
        if data.get("recommended") is None:
            assert data.get("agent_hint")

    def test_service_stop_idempotent_json(self) -> None:
        root = _find_repo_root()
        r = subprocess.run(
            [sys.executable, str(_SCRIPT), "--json", "service", "stop"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout.strip())
        assert data.get("ok") is True
        assert data.get("error_code") == "no_logging_session"
        assert "agent_hint" in data

    def test_service_tail_no_session_json(self) -> None:
        root = _find_repo_root()
        r = subprocess.run(
            [sys.executable, str(_SCRIPT), "--json", "service", "tail", "-n", "5"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 1, r.stderr
        data = json.loads(r.stdout.strip())
        assert data.get("ok") is False
        assert data.get("error_code") == "no_active_session"
        assert data.get("agent_hint")

    def test_list_devices_json_schema_with_or_without_hardware(self) -> None:
        """With no USB serial, expect failure JSON; with ports, expect success + hints."""
        root = _find_repo_root()
        r = subprocess.run(
            [sys.executable, str(_SCRIPT), "--json", "list-devices"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode in (0, 1), r.stderr
        data = json.loads(r.stdout.strip())
        if data.get("ok") is True:
            assert "ports" in data
            assert "hardware_connected" in data
            assert "t5_target_connected" in data
            assert "agent_hint" in data
        else:
            assert data.get("error_code") in (
                "no_serial_ports",
                "pyserial_missing",
                "t5_default_uart_not_found",
                "device_not_found",
            )
            assert data.get("agent_hint")
            assert data.get("t5_target_connected") is False
