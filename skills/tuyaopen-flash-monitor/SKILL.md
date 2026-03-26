---
name: tuyaopen-flash-monitor
description: >-
  Flash firmware to TuyaOpen devices and view serial device logs. Use when the
  user mentions flashing, burning firmware, tos.py flash, viewing device logs,
  serial monitor, tos.py monitor, or device authorization.
  固件烧录、刷固件、串口日志、设备日志、设备授权。
license: Apache-2.0
compatibility:
  - TuyaOpen environment activated (export.sh)
  - Device connected via USB
  - Serial port permission (Linux: user in dialout group)
---

# TuyaOpen Flash & Monitor

Docs: <https://tuyaopen.ai/zh/docs/quick-start/firmware-burning> | <https://tuyaopen.ai/zh/docs/quick-start/device-debug>

## Prerequisites

- Project built successfully (`tos.py build`).
- Device connected via USB.
- Current directory is the project directory (where you ran `tos.py build`).

## Serial Port Permission (Linux / Mac)

Required once, then **reboot**:

```bash
sudo usermod -aG dialout $USER
```

## Flashing Firmware

```bash
tos.py flash                        # auto-detect serial port
tos.py flash -p /dev/ttyACM0        # specify port
tos.py flash -b 921600              # specify baud rate (no special requirement)
tos.py flash -d                     # debug output
```

The flash tool `tyutool_cli` lives in `tools/tyutool/` and is auto-downloaded on first use. It selects the correct flash method based on the project's platform config.

Flash baud rate has **no special per-chip requirement** — the tool handles it automatically.

## Viewing Device Logs (Monitor)

```bash
tos.py monitor                      # auto-detect serial port
tos.py monitor -p /dev/ttyACM1      # specify port
tos.py monitor -b 460800            # specify baud rate (chip-dependent!)
```

Reset the device after starting monitor to capture full boot logs.

**Exit**: press `Ctrl+C` then press **Enter**.

### Monitor Baud Rate by Chip

**The monitor baud rate varies by chip platform.** Using the wrong baud rate will produce garbled output or no output at all.

| Chip | Debug UART | Monitor baud rate | Notes |
|------|-----------|-------------------|-------|
| Ubuntu (LINUX) | — | — | Runs natively on host, no serial needed |
| T2 | UART2 | 115200 | |
| T3 | UART1 | 460800 | |
| T5AI | UART1 | 460800 | |
| ESP32 / ESP32-C3 / ESP32-S3 | UART0 | 115200 | |
| LN882H | UART1 | 921600 | |
| BK7231N | UART2 | 115200 | |

### Writing Authorization Codes

`tos.py monitor` also supports writing device authorization codes (UUID / AuthKey) via the serial console. See the device authorization docs for the exact flow.

## T5 Series: Dual Serial Ports

T5 official dev boards use a **dual-port USB-UART chip**, exposing **two serial ports** when connected. One is for flash/authorization, the other is for monitor (log output).

### Typical mapping (not guaranteed)

| OS | Flash / Auth port (typical) | Monitor / Log port (typical) |
|----|---------------------------|------------------------------|
| Windows | Lower COM number (e.g. `COM3`) | Higher COM number (e.g. `COM4`) |
| Linux | `ttyACM0` | `ttyACM1` |

### Important: port assignment is NOT deterministic

The mapping above is the **common case**, but it is **not guaranteed**. The actual assignment depends on USB enumeration order, hub topology, and driver behavior. It may vary between machines or even between plug-in events on the same machine.

### Agent strategy for port identification

1. List available ports: `ls /dev/ttyACM*` (Linux) or check Device Manager (Windows).
2. **Try flash first** with the typical port (lower number). If `tos.py flash` reports an error or times out, swap to the other port.
3. **Try monitor** with the other port. If output is garbled, check the baud rate (see table above). If no output at all, swap ports.
4. If **both attempts fail**, ask the user which port is which. The user can physically check by pressing reset and seeing which port produces log output.

## ESP32 Platform: idf.py Passthrough

For ESP32 targets, `tos.py idf` passes commands directly to `idf.py`:

```bash
tos.py idf <idf_subcommand> [args]
```

This is useful for ESP32-specific operations not covered by `tos.py` itself.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Port [xxx] may be busy` | Serial port mapping not complete | Wait ~1 minute, retry |
| Garbled monitor output | Wrong baud rate | Check the baud rate table above for your chip |
| No monitor output | Wrong serial port selected | Swap to the other port; reset the device |
| Flash fails | Missing USB driver | Install platform-specific driver (see docs) |
| VM serial delay (T5) | USB passthrough latency | Device visible in `ls /dev/tty*` but busy — wait ~1 minute |
| `tyutool_gui` flagged as virus | Windows Defender false positive | Move to non-system drive; add to exclusions |
| Both ports fail | Non-standard hardware or cable issue | Ask user to identify ports manually |
