#!/usr/bin/env python3
# coding=utf-8
"""
hardware_target_base.py — Abstract hardware target for agent_target_tool.

Subclasses (e.g. target_t5.TuyaT5Target, future target_raspi5) implement baud rates,
USB identification, and monitor port selection. This module stays free of Tuya T5
constants so new boards stay isolated in their own files.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class PortInfo:
    device: str
    vid: Optional[int] = None
    pid: Optional[int] = None
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    product: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"device": self.device}
        if self.vid is not None:
            d["vid"] = f"0x{self.vid:04x}"
            d["vid_int"] = self.vid
        if self.pid is not None:
            d["pid"] = f"0x{self.pid:04x}"
            d["pid_int"] = self.pid
        if self.serial_number:
            d["serial_number"] = self.serial_number
        if self.manufacturer:
            d["manufacturer"] = self.manufacturer
        if self.product:
            d["product"] = self.product
        if self.description:
            d["description"] = self.description
        return d


VLog = Callable[[bool, str], None]


@dataclass(frozen=True)
class TosFlashCliArgs:
    """
    Arguments for `tos.py flash` (see tools/cli_command/cli_flash.py).

    Maps to: flash [-d] [-p PORT] [-b BAUD]
    """

    port: str = ""
    baud: int = 0
    debug: bool = False


class HardwareTarget(ABC):
    """
    One hardware family: default bauds, port heuristics, and monitor resolution.

    Override pick_default_monitor_port for non-generic USB identification (e.g. fixed VID/PID).
    """

    name: str = "generic"

    @abstractmethod
    def monitor_baud(self) -> int:
        """Default UART baud for log/monitor capture."""

    @abstractmethod
    def flash_baud_default(self) -> int:
        """0 = let tos.py / board config decide."""

    def port_match_score(self, p: PortInfo) -> int:
        """Higher = better guess when sorting or using --allow-any-serial fallback."""
        return 0

    def expected_usb_uart_meta(self) -> Optional[Dict[str, Any]]:
        """
        If this target has a well-known onboard USB–UART, return JSON-friendly VID/PID metadata.
        Used in device_not_found and list-devices payloads. Return None if not applicable.
        """
        return None

    def build_tos_flash_argv(self, cli: TosFlashCliArgs) -> List[str]:
        """
        Build argv tokens after the literal ``flash`` subcommand for ``tos.py``.

        Default matches ``cli_flash.cli``: optional -d, -p, -b. Baud 0 means omit -b
        (tos uses board ``tyutool.cfg`` / CONFIG_FLASH_BAUDRATE).
        """
        out: List[str] = []
        if cli.debug:
            out.append("-d")
        port = (cli.port or "").strip()
        if port:
            out.extend(["-p", port])
        if cli.baud and cli.baud > 0:
            out.extend(["-b", str(cli.baud)])
        return out

    def pick_default_monitor_port(
        self,
        all_ports: List[PortInfo],
        allow_any_serial: bool,
        verbose: bool,
        vlog: VLog,
        lines: List[str],
    ) -> Tuple[Optional[PortInfo], str]:
        """
        Choose the monitor serial port after global enumeration lines are already in `lines`.

        Appends target-specific discovery lines to `lines`. Returns (chosen_port, fail_reason_code).
        fail_reason_code is "" on success; otherwise e.g. t5_default_uart_not_found.
        """
        best = max(all_ports, key=lambda x: self.port_match_score(x))
        lines.append(f"Selected port (heuristic): {best.device}")
        vlog(verbose, lines[-1])
        return best, ""


class UnimplementedHardwareTarget(HardwareTarget):
    """
    Stub for targets not yet wired (e.g. Raspberry Pi 5). Subclass and implement methods,
    then register the factory in agent_target_tool.TARGETS.
    """

    name = "unimplemented"

    def monitor_baud(self) -> int:
        raise NotImplementedError("Subclass UnimplementedHardwareTarget and implement monitor_baud()")

    def flash_baud_default(self) -> int:
        raise NotImplementedError("Subclass UnimplementedHardwareTarget and implement flash_baud_default()")
