#!/usr/bin/env python3
# coding=utf-8
"""
cli_debug.py — Send commands to the TuyaOpen device serial CLI and capture responses.

The TuyaOpen firmware exposes a CLI on UART0 (for most platforms). Commands are
sent over the same USB-serial connection used for flashing and monitoring.

Usage:
    python cli_debug.py [options] <command>
    python cli_debug.py [options] help
    python cli_debug.py [options] send <command_string>

Sub-commands:
    help                 Send 'help' and print all available CLI commands.
    send <cmd>           Send a single CLI command and print the response.
    list-ports           List candidate serial ports without opening one.
    raw <text>           Send raw text (no newline auto-append).

Options:
    -p, --port <dev>     Serial port (e.g. /dev/ttyACM0). Auto-detected if omitted.
    -b, --baud <rate>    Baud rate. Default: 115200 (hardcoded in
                         TuyaOpen/src/tal_cli/src/tal_cli.c:811 for ALL platforms).
    --timeout <sec>      Seconds to wait for prompt after sending command. Default: 3.
    --json               Output results as JSON (useful for agent callers).
    -v, --verbose        Print port discovery and timing details to stderr.

Requirements:
    pip install pyserial

CONFIG NOTE:
    The TuyaOpen serial CLI is controlled by CONFIG_ENABLE_SERIAL_CLI_CMD in Kconfig.
    If `help` returns nothing or "unknown command", verify your app_default.config has:

        CONFIG_ENABLE_SERIAL_CLI_CMD=y

    Optional per-feature gates:
        CONFIG_CLI_CMD_SYS=y      (sys_* commands: sys_reset, sys_version, ...)
        CONFIG_CLI_CMD_FS=y       (fs_* filesystem commands)
        CONFIG_CLI_CMD_KV=y       (kv_* key-value store commands)

    After changing config, rebuild and reflash: tos.py clean -f && tos.py build && tos.py flash
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import List, Optional, Tuple

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print(
        'ERROR: pyserial not installed. Run: pip install pyserial',
        file=sys.stderr
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# TuyaOpen tal_cli hardcodes 115200 on ALL platforms.
# Source: TuyaOpen/src/tal_cli/src/tal_cli.c:811 — `cfg.base_cfg.baudrate = 115200;`
CLI_BAUD = 115200

# T5AI: WCH CH34x dual-serial VID/PID (one device exposes two ttyACM)
T5_VID = 0x1A86
T5_PID = 0x55D2

# Common USB-UART VID/PID pairs (informational for `list-ports` scoring)
COMMON_SERIAL_IDS = {
    (0x10C4, 0xEA60): 'CP210x',
    (0x1A86, 0x7523): 'CH340',
    (0x0403, 0x6001): 'FT232',
    (0x303A, 0x1001): 'Espressif USB-JTAG',
}


# ---------------------------------------------------------------------------
# Port discovery
# ---------------------------------------------------------------------------

def _vlog(verbose: bool, msg: str) -> None:
    if verbose:
        print(f'[cli_debug] {msg}', file=sys.stderr)


def list_candidate_ports(verbose: bool = False) -> List[dict]:
    """Return a list of dicts describing candidate serial ports."""
    ports = serial.tools.list_ports.comports()
    candidates = []
    for p in ports:
        info = {
            'device': p.device,
            'description': p.description or '',
            'vid': f'0x{p.vid:04x}' if p.vid else None,
            'pid': f'0x{p.pid:04x}' if p.pid else None,
            'serial_number': p.serial_number or '',
        }
        vid = p.vid
        pid = p.pid
        score = 0

        if 'ttyACM' in p.device or 'ttyUSB' in p.device:
            score += 5
        if re.match(r'^COM\d+$', p.device, re.I):
            score += 5

        if vid == T5_VID and pid == T5_PID:
            score += 60
            info['note'] = 'T5AI default WCH dual-serial bridge'
        elif vid is not None and pid is not None:
            label = COMMON_SERIAL_IDS.get((vid & 0xFFFF, pid & 0xFFFF))
            if label:
                score += 10
                info['note'] = label

        info['score'] = score
        if score > 0:
            candidates.append(info)
        _vlog(verbose, f'Port {p.device}: score={score} vid={info["vid"]} pid={info["pid"]}')

    candidates.sort(key=lambda x: (-x['score'], x['device']))
    return candidates


def pick_port(verbose: bool = False) -> Optional[str]:
    """
    Auto-pick the best monitor/CLI serial port.

    For T5AI: The dual-serial board exposes two ACM ports. The HIGHER-numbered
    port is typically the log/monitor/CLI port; the lower port is for flashing.
    (This is a heuristic — swap with -p if output is garbled.)
    """
    candidates = list_candidate_ports(verbose)
    if not candidates:
        return None

    # For T5AI: group T5 ports and pick the highest-numbered
    t5_ports = [c for c in candidates if 'T5AI' in c.get('note', '').upper()
                or (c.get('vid') == f'0x{T5_VID:04x}' and c.get('pid') == f'0x{T5_PID:04x}')]
    if t5_ports:
        def _num(d: str) -> int:
            m = re.search(r'(\d+)$', d)
            return int(m.group(1)) if m else 0
        t5_ports.sort(key=lambda c: -_num(c['device']))  # highest number first
        chosen = t5_ports[0]['device']
        _vlog(verbose, f'T5AI dual-serial: picked higher-numbered port {chosen} for CLI/monitor')
        return chosen

    return candidates[0]['device'] if candidates else None


# ---------------------------------------------------------------------------
# CLI interaction
# ---------------------------------------------------------------------------

# Prompt patterns emitted by various TuyaOpen CLI implementations
_PROMPT_PATTERNS = [
    re.compile(rb'tuya>\s*$'),
    re.compile(rb'#\s*$'),
    re.compile(rb'\$\s*$'),
    re.compile(rb'cli>\s*$'),
    re.compile(rb'>\s*$'),
]

# Detect if no CLI response (device doesn't have CLI enabled)
_NO_CLI_HINTS = [
    b'unknown command',
    b'command not found',
]


def _has_prompt(data: bytes) -> bool:
    for p in _PROMPT_PATTERNS:
        if p.search(data):
            return True
    return False


class DeviceCLI:
    """Context manager for interacting with the device CLI."""

    def __init__(self, port: str, baud: int, verbose: bool = False):
        self.port = port
        self.baud = baud
        self.verbose = verbose
        self._ser: Optional[serial.Serial] = None

    def __enter__(self) -> 'DeviceCLI':
        _vlog(self.verbose, f'Opening {self.port} @ {self.baud} baud')
        try:
            self._ser = serial.Serial(
                self.port, self.baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False, rtscts=False, dsrdtr=False,
                timeout=0.1,
            )
        except serial.SerialException as e:
            raise RuntimeError(f'Cannot open {self.port}: {e}') from e
        return self

    def __exit__(self, *args: object) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()

    def _read_until_quiet(self, timeout: float) -> bytes:
        """
        Read until no new data arrives for 0.3s, or until we see a CLI prompt,
        or until timeout.

        This separates command response from free-running log output:
        - We send the command then wait
        - Free-running logs continue in the background; we capture everything
        - Prompt detection tells us the response is complete
        """
        buf = b''
        deadline = time.time() + timeout
        last_data = time.time()
        quiet_after = 0.3  # Stop if no data for 300ms after some data arrives

        while time.time() < deadline:
            chunk = self._ser.read(1024)
            if chunk:
                buf += chunk
                last_data = time.time()
                _vlog(self.verbose, f'  Read {len(chunk)} bytes (total {len(buf)})')
                if _has_prompt(buf):
                    _vlog(self.verbose, '  CLI prompt detected')
                    break
            else:
                # Check quiet threshold
                if buf and (time.time() - last_data) > quiet_after:
                    break

        return buf

    def send(self, command: str, timeout: float = 3.0) -> Tuple[str, bool]:
        """
        Send a CLI command, wait for the response.

        Returns:
            (response_text, cli_seems_active)
            cli_seems_active: False if no response was received (CLI not enabled)
        """
        assert self._ser is not None

        # Clear any pending input
        self._ser.reset_input_buffer()

        cmd_bytes = (command.strip() + '\r\n').encode('utf-8')
        _vlog(self.verbose, f'Sending: {repr(cmd_bytes)}')
        self._ser.write(cmd_bytes)

        raw = self._read_until_quiet(timeout)
        text = raw.decode('utf-8', errors='replace')

        # Check if CLI responded at all
        cli_active = bool(raw.strip()) or _has_prompt(raw)

        # Also check for "unknown command" style errors
        for hint in _NO_CLI_HINTS:
            if hint in raw.lower():
                cli_active = True  # CLI is there, just unknown command

        return text, cli_active

    def wake_cli(self, retries: int = 3) -> bool:
        """
        Send blank lines to wake the CLI and detect if it responds.
        Returns True if the CLI appears active.
        """
        for i in range(retries):
            _, active = self.send('', timeout=1.5)
            if active:
                _vlog(self.verbose, f'CLI responded after {i+1} wake attempt(s)')
                return True
            time.sleep(0.3)
        return False


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _clean_response(text: str, command: str) -> str:
    """Strip the echo of the sent command from the response."""
    lines = text.splitlines()
    cleaned = []
    echo_seen = False
    for line in lines:
        stripped = line.strip()
        # Skip the echo of our command
        if not echo_seen and command.strip() in stripped:
            echo_seen = True
            continue
        cleaned.append(line)
    return '\n'.join(cleaned).strip()


def _output(data: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        if not data.get('ok', True):
            print(f'ERROR: {data.get("error", "unknown error")}', file=sys.stderr)
            if 'hint' in data:
                print(f'Hint: {data["hint"]}', file=sys.stderr)
        else:
            if 'output' in data:
                print(data['output'])
            if 'ports' in data:
                for p in data['ports']:
                    note = f'  [{p.get("note", "")}]' if p.get('note') else ''
                    print(f'  {p["device"]}{note}  vid={p.get("vid")} pid={p.get("pid")}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Send commands to TuyaOpen device CLI over UART.'
    )
    parser.add_argument('subcommand', choices=['help', 'send', 'list-ports', 'raw'],
                        help='Sub-command')
    parser.add_argument('command_args', nargs='*', help='Arguments for send/raw sub-commands')
    parser.add_argument('-p', '--port', help='Serial port (auto-detected if omitted)')
    parser.add_argument('-b', '--baud', type=int, default=CLI_BAUD,
                        help=f'Baud rate (default: {CLI_BAUD} — hardcoded by tal_cli.c on all platforms)')
    parser.add_argument('--timeout', type=float, default=3.0,
                        help='Seconds to wait for CLI response (default: 3)')
    parser.add_argument('--json', action='store_true', dest='as_json',
                        help='Output results as JSON')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    # ---- list-ports ----
    if args.subcommand == 'list-ports':
        candidates = list_candidate_ports(verbose=args.verbose)
        result = {'ok': True, 'ports': candidates}
        _output(result, args.as_json)
        if not args.as_json:
            print(f'\n{len(candidates)} candidate port(s) found.')
        return 0

    # ---- Resolve port ----
    port = args.port or pick_port(verbose=args.verbose)
    if not port:
        result = {
            'ok': False,
            'error': 'No serial port found.',
            'hint': (
                'Connect the device via USB and retry. '
                'On Linux, ensure you are in the "dialout" group: '
                'sudo usermod -aG dialout $USER && (re-login or newgrp dialout)'
            )
        }
        _output(result, args.as_json)
        return 1

    baud = args.baud  # default = CLI_BAUD = 115200
    if args.verbose:
        _vlog(True, f'Using port={port} baud={baud}')

    # ---- Open CLI ----
    try:
        cli = DeviceCLI(port, baud, args.verbose)
    except Exception as e:
        result = {'ok': False, 'error': str(e)}
        _output(result, args.as_json)
        return 1

    with cli:
        # ---- help ----
        if args.subcommand == 'help':
            _vlog(args.verbose, 'Waking CLI...')
            cli.wake_cli()
            response, cli_active = cli.send('help', timeout=args.timeout)

            if not cli_active:
                result = {
                    'ok': False,
                    'error': 'No response from device CLI.',
                    'hint': (
                        'No data received. Possible causes:\n'
                        '  1. CONFIG_ENABLE_SERIAL_CLI_CMD=y is not set — rebuild firmware.\n'
                        '  2. Wrong port — try the other ACM port with -p.\n'
                        '  3. Device is powered off, not booted, or stuck in panic.\n'
                        '  4. Port is held by another process (e.g. tos.py monitor).\n'
                        'tal_cli always runs at 115200 baud on every platform — '
                        'no need to try other rates.\n'
                        'After fixing config: tos.py clean -f && tos.py build && tos.py flash'
                    )
                }
                _output(result, args.as_json)
                return 1

            cleaned = _clean_response(response, 'help')
            result = {
                'ok': True,
                'port': port,
                'baud': baud,
                'command': 'help',
                'output': cleaned,
                'raw': response,
            }
            _output(result, args.as_json)
            return 0

        # ---- send ----
        elif args.subcommand == 'send':
            if not args.command_args:
                print('ERROR: send requires a command argument, e.g.: send "sys_reset"',
                      file=sys.stderr)
                return 1
            command = ' '.join(args.command_args)
            _vlog(args.verbose, f'Sending command: {command!r}')
            cli.wake_cli(retries=1)
            response, cli_active = cli.send(command, timeout=args.timeout)

            if not cli_active:
                result = {
                    'ok': False,
                    'error': f'No response to command: {command!r}',
                    'hint': (
                        'Device CLI did not respond. Check CONFIG_ENABLE_SERIAL_CLI_CMD=y, '
                        'port, and baud rate.'
                    )
                }
                _output(result, args.as_json)
                return 1

            cleaned = _clean_response(response, command)
            result = {
                'ok': True,
                'port': port,
                'baud': baud,
                'command': command,
                'output': cleaned,
                'raw': response,
            }
            _output(result, args.as_json)
            return 0

        # ---- raw ----
        elif args.subcommand == 'raw':
            if not args.command_args:
                print('ERROR: raw requires text argument', file=sys.stderr)
                return 1
            text = ' '.join(args.command_args)
            cli._ser.write(text.encode('utf-8'))  # type: ignore[union-attr]
            raw = cli._read_until_quiet(args.timeout)
            result = {
                'ok': True,
                'port': port,
                'baud': baud,
                'raw_output': raw.decode('utf-8', errors='replace'),
            }
            _output(result, args.as_json)
            return 0

    return 0


if __name__ == '__main__':
    sys.exit(main())
