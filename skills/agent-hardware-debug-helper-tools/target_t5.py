#!/usr/bin/env python3
# coding=utf-8
"""
target_t5.py — Tuya T5 / T5AI USB–UART and monitor heuristics for agent_target_tool.

Typical dev boards use a WCH CH34x dual virtual COM (VID 0x1a86, PID 0x55d2).
Monitor UART is commonly 460800 baud; lower-enumerated port is often flash, higher is log.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from hardware_target_base import HardwareTarget, PortInfo, TosFlashCliArgs, VLog

# ---------------------------------------------------------------------------
# T5 default USB–UART bridge (WCH dual-serial)
# ---------------------------------------------------------------------------
TUYA_T5_DEFAULT_USB_UART_VID = 0x1A86
TUYA_T5_DEFAULT_USB_UART_PID = 0x55D2


def is_t5_default_usb_uart(p: PortInfo) -> bool:
    """True if this port is the standard T5 onboard USB–UART (WCH dual-serial)."""
    if p.vid is None or p.pid is None:
        return False
    return (p.vid & 0xFFFF) == TUYA_T5_DEFAULT_USB_UART_VID and (
        p.pid & 0xFFFF
    ) == TUYA_T5_DEFAULT_USB_UART_PID


def t5_default_usb_uart_meta() -> Dict[str, Any]:
    return {
        "vid": f"0x{TUYA_T5_DEFAULT_USB_UART_VID:04x}",
        "pid": f"0x{TUYA_T5_DEFAULT_USB_UART_PID:04x}",
        "vid_int": TUYA_T5_DEFAULT_USB_UART_VID,
        "pid_int": TUYA_T5_DEFAULT_USB_UART_PID,
        "note": "Default T5/T5AI USB–UART (WCH CH34x dual serial).",
    }


def _monitor_port_preference_key(p: PortInfo) -> Tuple[int, str]:
    """
    Prefer higher-enumerated interface for monitor (typical: higher COM / ttyACM1).
    See tuyaopen-flash-monitor: lower port often flash, higher often log/monitor.
    """
    dev = p.device or ""
    m = re.search(r"(\d+)$", dev)
    n = int(m.group(1)) if m else 0
    return (-n, dev)


def pick_t5_monitor_port(candidates: List[PortInfo]) -> Optional[PortInfo]:
    """Among T5 default-bridge ports, pick the best guess for debug/monitor UART."""
    if not candidates:
        return None
    return sorted(candidates, key=_monitor_port_preference_key)[0]


# ---------------------------------------------------------------------------
# tos.py flash CLI (see tools/cli_command/cli_flash.py: flash [-d] [-p PORT] [-b BAUD])
# ---------------------------------------------------------------------------
# Board default baud comes from boards/<PLATFORM>/<BOARD>/tyutool.cfg (CONFIG_FLASH_BAUDRATE).
# Example explicit baud used in docs; pass baud=0 in TosFlashCliArgs to omit -b and use cfg.
T5_TOS_FLASH_TYPICAL_BAUD = 921600


class TuyaT5Target(HardwareTarget):
    """
    Tuya T5 / T5AI family (dual USB-UART common on dev boards).
    Monitor UART is typically 460800 (see tuyaopen-flash-monitor skill).
    """

    name = "tuya_t5"

    def monitor_baud(self) -> int:
        return 460800

    def flash_baud_default(self) -> int:
        return 0

    def expected_usb_uart_meta(self) -> Optional[Dict[str, Any]]:
        return t5_default_usb_uart_meta()

    def build_tos_flash_argv(self, cli: TosFlashCliArgs) -> List[str]:
        """
        Build argv tokens after ``tos.py flash`` for T5/T5AI.

        Matches ``cli_flash.cli``. On dual WCH USB–UART boards, the **flash** port is often
        the **lower** ``ttyACM`` / **lower COM number**; monitor/log uses the other interface
        (see tuyaopen-flash-monitor skill).
        """
        return super().build_tos_flash_argv(cli)

    def port_match_score(self, p: PortInfo) -> int:
        score = 0
        if p.device and ("ttyACM" in p.device or "ttyUSB" in p.device):
            score += 5
        if p.device and re.match(r"^COM\d+$", p.device, re.I):
            score += 5
        if is_t5_default_usb_uart(p):
            score += 60
            return score
        common = {
            (0x10C4, 0xEA60),  # CP210x
            (0x1A86, 0x7523),  # CH340 (single)
            (0x0403, 0x6001),  # FT232
            (0x303A, 0x1001),  # Espressif USB-JTAG (some configs)
        }
        if p.vid is not None and p.pid is not None:
            if (p.vid & 0xFFFF, p.pid & 0xFFFF) in common:
                score += 10
        return score

    def pick_default_monitor_port(
        self,
        all_ports: List[PortInfo],
        allow_any_serial: bool,
        verbose: bool,
        vlog: VLog,
        lines: List[str],
    ) -> Tuple[Optional[PortInfo], str]:
        t5_ports = [p for p in all_ports if is_t5_default_usb_uart(p)]
        lines.append(
            f"Looking for T5 default USB–UART (VID 0x{TUYA_T5_DEFAULT_USB_UART_VID:04x}, "
            f"PID 0x{TUYA_T5_DEFAULT_USB_UART_PID:04x}): found {len(t5_ports)} matching interface(s)."
        )
        vlog(verbose, lines[-1])
        if t5_ports:
            chosen = pick_t5_monitor_port(t5_ports)
            if chosen:
                lines.append(
                    f"Selected monitor port: {chosen.device} "
                    "(preference: higher COM / ttyACM index for typical dual-UART layout)."
                )
                vlog(verbose, lines[-1])
            return chosen, ""

        msg = (
            "device not found: no USB serial interface with "
            f"VID 0x{TUYA_T5_DEFAULT_USB_UART_VID:04x} and PID 0x{TUYA_T5_DEFAULT_USB_UART_PID:04x} "
            "(expected T5 onboard WCH dual-serial USB–UART)."
        )
        lines.append(msg)
        vlog(verbose, msg)
        if allow_any_serial:
            best = max(all_ports, key=lambda p: self.port_match_score(p))
            lines.append(
                f"Fallback (--allow-any-serial): using {best.device} (heuristic score, not T5 default bridge)."
            )
            vlog(verbose, lines[-1])
            return best, ""

        return None, "t5_default_uart_not_found"


def build_t5_tos_flash_argv(cli: TosFlashCliArgs) -> List[str]:
    """
    Module helper: argv tokens after ``flash`` for ``python tos.py flash …``.

    Delegates to :meth:`TuyaT5Target.build_tos_flash_argv`.
    """
    return TuyaT5Target().build_tos_flash_argv(cli)
