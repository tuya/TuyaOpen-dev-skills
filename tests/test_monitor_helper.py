import json
import os
import sys
import unittest.mock as mock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "tuyaopen", "debug-helper", "scripts"))
import monitor_helper


@pytest.fixture(autouse=True)
def isolated_session(tmp_path, monkeypatch):
    """Redirect session files to a temp dir for each test."""
    monkeypatch.setattr(monitor_helper, "SESSION_DIR", str(tmp_path))
    monkeypatch.setattr(monitor_helper, "SESSION_FILE", str(tmp_path / "session.json"))


def test_load_session_no_file():
    assert monitor_helper._load_session() is None


def test_save_and_load_session(tmp_path):
    monitor_helper._save_session(1234, str(tmp_path / "device.log"))
    session = monitor_helper._load_session()
    assert session["pid"] == 1234
    assert "device.log" in session["log_file"]


def test_clear_session():
    monitor_helper._save_session(1234, "device.log")
    monitor_helper._clear_session()
    assert monitor_helper._load_session() is None


def test_status_no_session(capsys):
    monitor_helper.cmd_status(as_json=True)
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["running"] is False


def test_stop_no_session(capsys):
    monitor_helper.cmd_stop(as_json=True)
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["message"] == "no active session"


def test_tail_no_session(capsys):
    with pytest.raises(SystemExit):
        monitor_helper.cmd_tail(n=10, as_json=True)
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "no active session" in out["error"]


def test_tail_reads_last_n_lines(tmp_path):
    log = tmp_path / "device.log"
    log.write_text("\n".join(f"line{i}" for i in range(10)) + "\n")
    monitor_helper._save_session(99999, str(log))

    captured = []
    def fake_out(data, as_json):
        captured.append(data)

    with mock.patch.object(monitor_helper, "_out", side_effect=fake_out):
        monitor_helper.cmd_tail(n=3, as_json=True)

    assert captured[0]["ok"] is True
    lines = captured[0]["text"].strip().splitlines()
    assert lines == ["line7", "line8", "line9"]


def test_project_root_finds_app_default_config(tmp_path):
    config = tmp_path / "app_default.config"
    config.write_text("")
    subdir = tmp_path / "src"
    subdir.mkdir()
    old = os.getcwd()
    os.chdir(subdir)
    try:
        result = monitor_helper._project_root()
        assert result == str(tmp_path)
    finally:
        os.chdir(old)


def test_project_root_falls_back_to_cwd(tmp_path):
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = monitor_helper._project_root()
        assert result == str(tmp_path)
    finally:
        os.chdir(old)
