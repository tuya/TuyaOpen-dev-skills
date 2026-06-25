#!/usr/bin/env python3
# coding=utf-8
"""
crash_decode.py — Decode TuyaOpen firmware crash dumps to source locations.

Supports: T5AI (BK7258, ARM Cortex-M), T2/T3/LN882H (ARM), ESP32/ESP32-S3 (Xtensa), LINUX.

Usage:
    python crash_decode.py [options] [<crash_dump_file>]

If no file is given, reads from stdin.

Options:
    --elf <path>        Path to ELF file (skip auto-discovery)
    --toolchain <path>  Path to addr2line binary (skip auto-discovery)
    --platform <name>   Platform hint: t5ai, esp32, t2, t3, ln882h, linux
    --nm                Also print nm symbol context for each address
    --dump-only         Only parse and print the addresses found, do not decode
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

# ARM Cortex-M register names appear in BK7258/T5AI/T2/T3/LN882H crash dumps
_ARM_CORTEX_M_REGS = re.compile(
    r'\b(PC|LR|SP|MSP|PSP|R0|R1|R2|R3|R4|R5|R6|R7|R8|R9|R10|R11|R12|XPSR|'
    r'CFSR|HFSR|DFSR|AFSR|MMAR|BFAR)\b'
)
# Xtensa register names appear in ESP32/ESP32-S3 crash dumps
_XTENSA_REGS = re.compile(r'\b(PC\s*:|EPC\d+|EXCVADDR|EXCCAUSE|a0|a1|a2|a3|a4|a5|'
                           r'a6|a7|a8|a9|a10|a11|a12|a13|a14|a15)\b')
_T5AI_FIRMWARE_NAME = re.compile(r'Firmware name:\s*(app@cpu1|app@cpu0|app)', re.I)
_BK7258_HINT = re.compile(r'bk7258|BK7258|t5ai|T5AI|t5_os', re.I)
_ESP32_HINT = re.compile(r'ESP-IDF|esp32|xtensa|Xtensa|EPC\d+', re.I)


def detect_platform(dump_text: str) -> str:
    """Return a platform slug: 't5ai', 'esp32', 't2', 't3', 'ln882h', 'linux', or 'arm'."""
    if _T5AI_FIRMWARE_NAME.search(dump_text) or _BK7258_HINT.search(dump_text):
        return 't5ai'
    if _ESP32_HINT.search(dump_text) or _XTENSA_REGS.search(dump_text):
        return 'esp32'
    arm_score = len(_ARM_CORTEX_M_REGS.findall(dump_text))
    if arm_score >= 3:
        return 'arm'  # Generic ARM — caller can override
    return 'unknown'


def is_cpu1_dump(dump_text: str) -> bool:
    """True if the dump is from the BK7258 AP (CPU1) core, not the primary CPU0."""
    return bool(re.search(r'app@cpu1|cpu1|bk7258_ap', dump_text, re.I))


# ---------------------------------------------------------------------------
# Toolchain discovery
# ---------------------------------------------------------------------------

def _find_bin(pattern: str) -> Optional[str]:
    """Glob for a binary; return first executable hit."""
    for p in sorted(glob.glob(pattern)):
        if os.access(p, os.X_OK):
            return p
    return None


def _search_dirs(dirs: List[str], name: str) -> Optional[str]:
    for d in dirs:
        candidate = os.path.join(d, name)
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def find_arm_addr2line(repo_root: Optional[str] = None) -> Optional[str]:
    """
    Locate arm-none-eabi-addr2line.

    Search order:
      1. TuyaOpen/platform/tools/*/bin/arm-none-eabi-addr2line  (preferred)
      2. $PATH
    """
    roots = []
    if repo_root:
        roots.append(repo_root)
    # Walk upward from cwd looking for TuyaOpen
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / 'TuyaOpen').is_dir():
            roots.append(str(candidate / 'TuyaOpen'))
            break
        if (candidate / 'tos.py').exists():
            roots.append(str(candidate))
            break

    for root in roots:
        hit = _find_bin(os.path.join(root, 'platform', 'tools', '*', 'bin', 'arm-none-eabi-addr2line'))
        if hit:
            return hit
        # Fallback: any GCC cross toolchain anywhere under platform/tools
        hit = _find_bin(os.path.join(root, 'platform', 'tools', '**', 'arm-none-eabi-addr2line'))
        if hit:
            return hit

    # System PATH
    from shutil import which
    return which('arm-none-eabi-addr2line')


def find_xtensa_addr2line(repo_root: Optional[str] = None) -> Optional[str]:
    """
    Locate xtensa-esp32s3-elf-addr2line (or xtensa-esp32-elf-addr2line).

    Searches:
      1. TuyaOpen/platform/ESP32/esp-idf/tools/  (local IDF)
      2. ~/.espressif/tools/  (standard ESP-IDF install)
      3. /opt/esp/tools/
      4. $IDF_PATH/tools/
      5. $PATH
    """
    search_roots: List[str] = []

    # IDF_PATH env
    idf_path = os.environ.get('IDF_PATH')
    if idf_path:
        search_roots.append(os.path.join(idf_path, 'tools'))

    # Local TuyaOpen clone
    roots = []
    if repo_root:
        roots.append(repo_root)
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / 'TuyaOpen').is_dir():
            roots.append(str(candidate / 'TuyaOpen'))
            break
        if (candidate / 'tos.py').exists():
            roots.append(str(candidate))
            break

    for r in roots:
        search_roots.append(os.path.join(r, 'platform', 'ESP32', 'esp-idf', 'tools'))
        search_roots.append(os.path.join(r, 'platform', 'tools'))

    # System Espressif
    home = Path.home()
    search_roots.append(str(home / '.espressif' / 'tools'))
    search_roots.append('/opt/esp/tools')

    for root in search_roots:
        for pattern in [
            os.path.join(root, '**', 'bin', 'xtensa-esp32s3-elf-addr2line'),
            os.path.join(root, '**', 'xtensa-esp32s3-elf-addr2line'),
            os.path.join(root, '**', 'bin', 'xtensa-esp32-elf-addr2line'),
            os.path.join(root, '**', 'xtensa-esp32-elf-addr2line'),
        ]:
            hit = _find_bin(pattern)
            if hit:
                return hit

    from shutil import which
    return which('xtensa-esp32s3-elf-addr2line') or which('xtensa-esp32-elf-addr2line')


def find_addr2line(platform: str, repo_root: Optional[str] = None) -> Optional[str]:
    if platform in ('esp32',):
        return find_xtensa_addr2line(repo_root)
    return find_arm_addr2line(repo_root)


# ---------------------------------------------------------------------------
# ELF discovery
# ---------------------------------------------------------------------------

def find_elf(platform: str, is_cpu1: bool, repo_root: Optional[str] = None) -> Optional[str]:
    """
    Locate the best ELF for decoding.

    Standard layout (TuyaOpen dist/):
      dist/*/debug/bk7258_ap/app.elf   — T5AI CPU1 (AP core)
      dist/*/debug/bk7258/app.elf      — T5AI CPU0
      dist/*/debug/*/app.elf           — Other platforms
      dist/*/*.elf                     — Single-CPU fallback

    Build-tree fallback:
      TuyaOpen/platform/*/build/**/*.elf
      .build/bin/*.elf
      .build/bin/debug/*/app.elf
    """
    search_dirs: List[str] = []
    if repo_root:
        search_dirs.append(repo_root)

    cwd = Path.cwd()
    # Find workspace root by looking for dist/ or tos.py
    for candidate in [cwd, *cwd.parents]:
        if (candidate / 'dist').is_dir():
            search_dirs.insert(0, str(candidate))
            break
        if (candidate / 'tos.py').exists():
            search_dirs.insert(0, str(candidate))
            break

    search_dirs.append(str(cwd))

    candidates: List[Tuple[int, str]] = []  # (priority, path)

    for root in search_dirs:
        dist = os.path.join(root, 'dist')
        if os.path.isdir(dist):
            # T5AI dual-core: prefer bk7258_ap if cpu1 dump, bk7258 otherwise
            if platform == 't5ai':
                if is_cpu1:
                    for p in glob.glob(os.path.join(dist, '*', 'debug', 'bk7258_ap', 'app.elf')):
                        candidates.append((10, p))
                    for p in glob.glob(os.path.join(dist, '*', 'debug', 'bk7258', 'app.elf')):
                        candidates.append((5, p))
                else:
                    for p in glob.glob(os.path.join(dist, '*', 'debug', 'bk7258', 'app.elf')):
                        candidates.append((10, p))
                    for p in glob.glob(os.path.join(dist, '*', 'debug', 'bk7258_ap', 'app.elf')):
                        candidates.append((5, p))
            # Any platform: dist/*/debug/*/app.elf
            for p in glob.glob(os.path.join(dist, '*', 'debug', '*', 'app.elf')):
                if p not in [c for _, c in candidates]:
                    candidates.append((3, p))
            # Single-CPU fallback
            for p in glob.glob(os.path.join(dist, '*', '*.elf')):
                candidates.append((1, p))

        # Build-tree fallback
        build = os.path.join(root, '.build')
        if os.path.isdir(build):
            for p in glob.glob(os.path.join(build, 'bin', 'debug', '*', 'app.elf')):
                candidates.append((2, p))
            for p in glob.glob(os.path.join(build, 'bin', '*.elf')):
                candidates.append((1, p))

        # TuyaOpen platform build tree
        tuya_open = os.path.join(root, 'TuyaOpen')
        if not os.path.isdir(tuya_open):
            tuya_open = root  # might already be TuyaOpen root
        for p in glob.glob(os.path.join(tuya_open, 'platform', '*', 'build', '**', 'app.elf')):
            candidates.append((2, p))

    if not candidates:
        return None

    # Sort by priority (descending), then mtime (newest first)
    candidates.sort(key=lambda x: (-x[0], -os.path.getmtime(x[1]) if os.path.exists(x[1]) else 0))
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Crash dump parsing
# ---------------------------------------------------------------------------

# Matches: "PC: 0x021d9094" or "PC = 0x021d9094" or just hex standalone
_REG_ADDR = re.compile(r'\b(PC|LR|EPC\d+)\s*[=:]\s*(0x[0-9a-fA-F]+|\b[0-9a-fA-F]{6,8}\b)')
# Stack frame lines: "addr: 0xXXXXXXXX  data: 0xXXXXXXXX"
_STACK_LINE = re.compile(r'addr:\s*(0x[0-9a-fA-F]+)\s+data:\s*(0x[0-9a-fA-F]+)')
# Bare hex lines that might be stack frames
_BARE_HEX = re.compile(r'\b(0x[0-9a-fA-F]{6,8})\b')


def _looks_like_code(addr: int, pc_range_hint: Tuple[int, int]) -> bool:
    """Heuristic: is this address in the same memory region as PC/LR (code flash)?"""
    lo, hi = pc_range_hint
    if lo == 0 and hi == 0:
        return True  # No hint, include all
    margin = max(0x200000, (hi - lo) * 2)
    return (lo - margin) <= addr <= (hi + margin)


def parse_addresses(dump_text: str) -> Tuple[List[Tuple[str, str]], List[str]]:
    """
    Returns:
        (register_addrs, stack_addrs)
        register_addrs: list of (name, hex_addr) for PC, LR, EPC*
        stack_addrs: list of hex_addr strings that look like code pointers
    """
    reg_addrs: List[Tuple[str, str]] = []
    seen_regs: set = set()

    for m in _REG_ADDR.finditer(dump_text):
        name = m.group(1)
        addr = m.group(2)
        if not addr.startswith('0x'):
            addr = '0x' + addr
        if name not in seen_regs:
            reg_addrs.append((name, addr))
            seen_regs.add(name)

    # Determine code range from PC/LR
    reg_values = []
    for name, addr in reg_addrs:
        try:
            reg_values.append(int(addr, 16))
        except ValueError:
            pass
    pc_range: Tuple[int, int] = (min(reg_values), max(reg_values)) if reg_values else (0, 0)

    # Parse stack lines
    stack_addrs: List[str] = []
    seen_stack: set = set()
    for m in _STACK_LINE.finditer(dump_text):
        data_addr = m.group(2)
        try:
            val = int(data_addr, 16)
        except ValueError:
            continue
        if _looks_like_code(val, pc_range) and data_addr not in seen_stack:
            stack_addrs.append(data_addr)
            seen_stack.add(data_addr)

    return reg_addrs, stack_addrs


# ---------------------------------------------------------------------------
# addr2line decode
# ---------------------------------------------------------------------------

def decode_addresses(addr2line: str, elf: str, addrs: List[str]) -> str:
    """Run addr2line for a list of hex addresses and return the raw output."""
    if not addrs:
        return ''
    cmd = [addr2line, '-e', elf, '-f', '-C', '-i'] + addrs
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.stdout
    except subprocess.TimeoutExpired:
        return '(addr2line timed out)'
    except FileNotFoundError:
        return f'(addr2line not found: {addr2line})'


def format_decoded(raw: str) -> str:
    """Format addr2line output into readable call frames."""
    lines = raw.strip().splitlines()
    frames = []
    i = 0
    frame_num = 0
    while i < len(lines):
        func = lines[i].strip() if i < len(lines) else '??'
        loc = lines[i + 1].strip() if (i + 1) < len(lines) else '??'
        frames.append(f'  #{frame_num:<2} {func}')
        frames.append(f'       at {loc}')
        i += 2
        frame_num += 1
    return '\n'.join(frames)


# ---------------------------------------------------------------------------
# nm symbol context
# ---------------------------------------------------------------------------

def nm_context(addr2line_path: str, elf: str, addr: str, window: int = 3) -> str:
    """Print nm symbols near the given address for context."""
    nm_bin = addr2line_path.replace('addr2line', 'nm')
    if not os.access(nm_bin, os.X_OK):
        return '(nm not found)'
    try:
        val = int(addr, 16)
    except ValueError:
        return '(invalid address)'

    try:
        result = subprocess.run(
            [nm_bin, '--demangle', '--numeric-sort', elf],
            capture_output=True, text=True, timeout=30
        )
    except Exception as e:
        return f'(nm error: {e})'

    symbols = []
    for line in result.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            sym_addr = int(parts[0], 16)
        except ValueError:
            continue
        sym_type = parts[1]
        sym_name = parts[2]
        if sym_type.upper() in ('T', 'W'):  # Code symbols only
            symbols.append((sym_addr, sym_name))

    # Find the closest symbols
    closest: List[Tuple[int, str]] = []
    for sym_addr, sym_name in symbols:
        if abs(sym_addr - val) < 0x10000:
            closest.append((sym_addr, sym_name))

    closest.sort(key=lambda x: abs(x[0] - val))
    nearby = closest[:window * 2]
    nearby.sort(key=lambda x: x[0])

    lines = []
    for sym_addr, sym_name in nearby:
        marker = ' <== ' if sym_addr <= val <= sym_addr + 0x200 else '     '
        lines.append(f'  {sym_addr:08x}{marker}{sym_name}')
    return '\n'.join(lines) if lines else '(no nearby code symbols)'


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description='Decode TuyaOpen firmware crash dumps.')
    parser.add_argument('dump_file', nargs='?', help='Crash dump text file (default: stdin)')
    parser.add_argument('--elf', help='Path to ELF file (skips auto-discovery)')
    parser.add_argument('--toolchain', help='Path to addr2line binary (skips auto-discovery)')
    parser.add_argument('--platform', choices=['t5ai', 'esp32', 't2', 't3', 'ln882h', 'linux', 'arm'],
                        help='Platform hint')
    parser.add_argument('--nm', action='store_true', help='Print nm symbol context for each address')
    parser.add_argument('--dump-only', action='store_true', help='Print parsed addresses and exit')
    args = parser.parse_args()

    # Read dump
    if args.dump_file:
        with open(args.dump_file) as f:
            dump_text = f.read()
    else:
        dump_text = sys.stdin.read()

    # Detect platform
    platform = args.platform or detect_platform(dump_text)
    is_cpu1 = is_cpu1_dump(dump_text)

    print(f'[crash_decode] Platform detected: {platform}' + (' (CPU1/AP core)' if is_cpu1 else ''))

    # Parse addresses
    reg_addrs, stack_addrs = parse_addresses(dump_text)

    if not reg_addrs and not stack_addrs:
        print('[crash_decode] No addresses found in dump.')
        print('  Expected: "PC: 0x..." / "LR: 0x..." lines and/or "addr: 0x...  data: 0x..." stack lines')
        return 1

    print(f'[crash_decode] Found {len(reg_addrs)} register addresses, {len(stack_addrs)} stack addresses')

    if args.dump_only:
        print('\nRegister addresses:')
        for name, addr in reg_addrs:
            print(f'  {name}: {addr}')
        print('\nStack addresses (possible code pointers):')
        for addr in stack_addrs:
            print(f'  {addr}')
        return 0

    # Find addr2line
    addr2line = args.toolchain or find_addr2line(platform)
    if not addr2line:
        print(f'[crash_decode] ERROR: addr2line not found for platform "{platform}".')
        if platform in ('esp32',):
            print('  Install ESP-IDF or set $IDF_PATH, or use --toolchain.')
        else:
            print('  Expected at: TuyaOpen/platform/tools/gcc-arm-none-eabi-*/bin/arm-none-eabi-addr2line')
            print('  Or install arm-none-eabi-binutils and ensure it is in $PATH.')
        return 1
    print(f'[crash_decode] Toolchain: {addr2line}')

    # Find ELF
    elf = args.elf or find_elf(platform, is_cpu1)
    if not elf or not os.path.exists(elf):
        print(f'[crash_decode] ERROR: ELF not found.')
        print('  Searched: dist/*/debug/**/app.elf, .build/bin/*.elf')
        print('  Use --elf <path> to specify explicitly.')
        print('  Note: Build with debug info enabled (CONFIG_DEBUG=y or equivalent).')
        return 1
    print(f'[crash_decode] ELF: {elf}')
    print()

    # --- Decode register addresses (PC, LR, etc.) ---
    if reg_addrs:
        print('=== Register Addresses (PC / LR / EPC) ===')
        reg_hex = [addr for _, addr in reg_addrs]
        raw = decode_addresses(addr2line, elf, reg_hex)
        raw_lines = raw.strip().splitlines()
        i = 0
        for j, (name, addr) in enumerate(reg_addrs):
            func = raw_lines[i].strip() if i < len(raw_lines) else '??'
            loc = raw_lines[i + 1].strip() if (i + 1) < len(raw_lines) else '??'
            print(f'  {name} = {addr}')
            print(f'    Function: {func}')
            print(f'    Location: {loc}')
            if args.nm:
                print(f'    Nearby symbols:\n{nm_context(addr2line, elf, addr)}')
            print()
            i += 2  # addr2line may emit multiple lines per address with -i

    # --- Decode stack addresses ---
    if stack_addrs:
        print(f'=== Stack Code Pointers ({len(stack_addrs)} candidates) ===')
        print('(Only addresses in the same memory range as PC/LR are included)')
        raw = decode_addresses(addr2line, elf, stack_addrs)
        raw_lines_all = raw.strip().splitlines()
        # Parse into per-address blocks (each address may yield 2+ lines with -i)
        # addr2line outputs func\nloc pairs; we label each address
        raw_per_addr = []
        raw_block = decode_addresses(addr2line, elf, stack_addrs[:1])
        # Count lines per address by doing one address test
        lines_per_addr = len(raw_block.strip().splitlines())
        idx = 0
        for addr in stack_addrs:
            block_lines = raw_lines_all[idx: idx + lines_per_addr]
            idx += lines_per_addr
            if block_lines:
                func = block_lines[0].strip()
                loc = block_lines[1].strip() if len(block_lines) > 1 else '??'
                if func != '??' and 'unknown' not in func.lower():
                    raw_per_addr.append((addr, func, loc))

        for addr, func, loc in raw_per_addr:
            print(f'  {addr}  →  {func}')
            print(f'            at {loc}')
        if not raw_per_addr:
            print('  (all stack addresses decoded to unknown — may be data, not code)')
        print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
