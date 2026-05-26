#!/usr/bin/env python3
"""Cross-platform background monitor helper for TuyaOpen agents.

Manages `tos.py monitor -l` as a background subprocess so agents can
capture device logs without blocking the terminal.

Commands:
  start -p <port> [-l <logfile>]   Start background monitor
  tail  [-n N]                     Read last N lines from log file
  stop                             Stop the monitor process
  status                           Check if monitor is running

Options:
  --json     Machine-readable JSON output

Logs and session state are stored under <project_dir>/.target_logging/,
where <project_dir> is the directory containing app_default.config.
The SDK .gitignore covers .target_logging at any depth (no leading slash).
"""
import argparse
import datetime
import json
import os
import subprocess
import sys


def _sdk_root():
    """Return SDK root from $OPEN_SDK_ROOT, or search upward for tos.py."""
    root = os.environ.get("OPEN_SDK_ROOT", "")
    if root and os.path.isfile(os.path.join(root, "tos.py")):
        return root
    d = os.path.abspath(os.path.dirname(__file__))
    while True:
        if os.path.isfile(os.path.join(d, "tos.py")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.getcwd()


def _project_root():
    """Return the project root (where app_default.config lives), searching upward from CWD.

    Falls back to CWD if not found. Logs belong to the project, not the SDK.
    The SDK .gitignore covers .target_logging/ at any depth (no leading slash),
    so logs are always gitignored regardless of project location.
    """
    d = os.path.abspath(os.getcwd())
    while True:
        if os.path.isfile(os.path.join(d, "app_default.config")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.getcwd()


_ROOT = _sdk_root()
SESSION_DIR = os.path.join(_project_root(), ".target_logging")
SESSION_FILE = os.path.join(SESSION_DIR, "session.json")


def _python_exe():
    """Venv Python: $OPEN_SDK_PYTHON (set by export.sh/ps1/bat), else sys.executable."""
    return os.environ.get("OPEN_SDK_PYTHON") or sys.executable


def _out(data, as_json):
    if as_json:
        print(json.dumps(data))
    else:
        for k, v in data.items():
            print(f"{k}: {v}")


def _load_session():
    if not os.path.isfile(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def _save_session(pid, log_file):
    os.makedirs(SESSION_DIR, exist_ok=True)
    with open(SESSION_FILE, "w") as f:
        json.dump({"pid": pid, "log_file": log_file}, f)


def _clear_session():
    try:
        os.remove(SESSION_FILE)
    except FileNotFoundError:
        pass


def _is_running(pid):
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, text=True,
        )
        return str(pid) in result.stdout
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def _stop_pid(pid):
    if not _is_running(pid):
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
            )
        else:
            os.kill(pid, 15)  # SIGTERM
    except Exception:
        pass


def cmd_start(port, log_file, as_json):
    session = _load_session()
    if session and _is_running(session["pid"]):
        _stop_pid(session["pid"])

    os.makedirs(SESSION_DIR, exist_ok=True)
    if not log_file:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(SESSION_DIR, f"{ts}.log")

    cmd = [_python_exe(), os.path.join(_ROOT, "tos.py"), "monitor", "-p", port, "-l", log_file]
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )
    _save_session(proc.pid, log_file)
    _out({"ok": True, "pid": proc.pid, "log_file": log_file}, as_json)


def cmd_stop(as_json):
    session = _load_session()
    if not session:
        _out({"ok": True, "message": "no active session"}, as_json)
        return
    _stop_pid(session["pid"])
    _clear_session()
    _out({"ok": True, "message": "stopped"}, as_json)


def cmd_tail(n, as_json):
    session = _load_session()
    if not session:
        _out({"ok": False, "error": "no active session"}, as_json)
        sys.exit(1)
    log_file = session["log_file"]
    if not os.path.isfile(log_file):
        _out({"ok": False, "error": f"log file not found: {log_file}"}, as_json)
        sys.exit(1)
    with open(log_file, errors="replace") as f:
        lines = f.readlines()
    text = "".join(lines[-n:])
    _out({"ok": True, "log_file": log_file, "text": text}, as_json)


def cmd_status(as_json):
    session = _load_session()
    if not session:
        _out({"ok": True, "running": False, "message": "no session"}, as_json)
        return
    running = _is_running(session["pid"])
    _out(
        {"ok": True, "running": running, "pid": session["pid"], "log_file": session["log_file"]},
        as_json,
    )


def main():
    parser = argparse.ArgumentParser(description="TuyaOpen background monitor helper")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start background monitor")
    p_start.add_argument("-p", "--port", required=True, help="Serial port")
    p_start.add_argument("-l", "--log", default=None, dest="log_file", help="Log file path")

    p_tail = sub.add_parser("tail", help="Tail log file")
    p_tail.add_argument("-n", type=int, default=200, help="Number of lines")

    sub.add_parser("stop", help="Stop background monitor")
    sub.add_parser("status", help="Check monitor status")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args.port, args.log_file, args.as_json)
    elif args.command == "stop":
        cmd_stop(args.as_json)
    elif args.command == "tail":
        cmd_tail(args.n, args.as_json)
    elif args.command == "status":
        cmd_status(args.as_json)


if __name__ == "__main__":
    main()
