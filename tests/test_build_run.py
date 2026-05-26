import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "tuyaopen", "dev-loop", "scripts"))
import build_run


def test_analyze_log_counts_errors():
    lines = [
        "[05-25 10:00:00 ty E][main.c:10] something failed\n",
        "[05-25 10:00:01 ty W][main.c:20] minor warning\n",
        "[05-25 10:00:02 ty I][main.c:30] feed watchdog\n",
        "[05-25 10:00:03 ty I][main.c:31] feed watchdog\n",
    ]
    errors, warns, wdts = build_run.analyze_log(lines)
    assert errors == 1
    assert warns == 1
    assert wdts == 2


def test_analyze_log_empty():
    errors, warns, wdts = build_run.analyze_log([])
    assert errors == 0
    assert warns == 0
    assert wdts == 0


def test_analyze_log_no_errors():
    lines = [
        "[05-25 10:00:02 ty I][main.c:30] feed watchdog\n",
        "[05-25 10:00:03 ty I][main.c:31] mqtt connected\n",
    ]
    errors, warns, wdts = build_run.analyze_log(lines)
    assert errors == 0
    assert warns == 0
    assert wdts == 1
