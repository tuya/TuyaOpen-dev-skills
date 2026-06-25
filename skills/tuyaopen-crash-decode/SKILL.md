---
name: tuyaopen-crash-decode
description: >-
  Decode TuyaOpen firmware crash dumps (PC, LR, stack addresses) to source
  file:line using the platform toolchain. Use when the user pastes a panic log,
  hard-fault dump, or register dump with hex addresses like "PC: 0x021d9094" or
  "addr: 0x... data: 0x...". Supports T5AI (BK7258/ARM Cortex-M), ESP32/S3
  (Xtensa), T2, T3, LN882H, and LINUX. 固件崩溃解码、panic、hard fault、PC/LR地址解析、addr2line。
license: Apache-2.0
compatibility:
  - TuyaOpen repository clone (dist/ or build tree with debug ELF)
  - ARM: arm-none-eabi-binutils in TuyaOpen/platform/tools/ (auto-downloaded by tos.py build)
  - ESP32: ESP-IDF installed ($IDF_PATH or ~/.espressif/) or xtensa-esp32*-elf in PATH
---

# TuyaOpen Crash Decode

Decodes a raw firmware panic / hard-fault log into readable source locations
(`file:line` + demangled function names) using `addr2line` from the platform
toolchain and the debug ELF produced by `tos.py build`.

## Quick start

```bash
# Paste crash dump, pipe to script (auto-discovers toolchain + ELF)
python skills/tuyaopen-crash-decode/crash_decode.py < crash.txt

# Or provide a dump file directly
python skills/tuyaopen-crash-decode/crash_decode.py crash.txt

# T5AI — only show parsed addresses, skip decoding
python skills/tuyaopen-crash-decode/crash_decode.py --dump-only crash.txt

# Override ELF and toolchain paths explicitly
python skills/tuyaopen-crash-decode/crash_decode.py \
  --elf dist/MyProject_1.0.0/debug/bk7258_ap/app.elf \
  --toolchain TuyaOpen/platform/tools/gcc-arm-none-eabi-10.3-2021.10/bin/arm-none-eabi-addr2line \
  crash.txt
```

## Step-by-step for an agent

1. **Capture the crash dump** — use `tuyaopen-flash-monitor` or `agent-hardware-debug-helper-tools` to capture the device log. A typical T5AI crash looks like:

   ```
   Firmware name: app@cpu1
   Exception Type: Data Abort
   PC: 0x021d9094
   LR: 0x021d1420
   SP: 0x3fff0a80
   ...
   addr: 0x3fff0a80  data: 0x021d1414
   addr: 0x3fff0a84  data: 0x021d9094
   ```

2. **Save the dump** and run `crash_decode.py`:

   ```bash
   python skills/tuyaopen-crash-decode/crash_decode.py crash.txt
   ```

3. **Read the output** — the script prints register address frames, then stack code-pointer candidates:

   ```
   [crash_decode] Platform detected: t5ai (CPU1/AP core)
   [crash_decode] Toolchain: TuyaOpen/platform/tools/gcc-arm-none-eabi-.../arm-none-eabi-addr2line
   [crash_decode] ELF: dist/DuckyClaw_1.0.0/debug/bk7258_ap/app.elf

   === Register Addresses (PC / LR / EPC) ===
     PC = 0x021d9094
       Function: lv_obj_get_scrollbar_mode
       Location: .../lv_obj_scroll.c:94

     LR = 0x021d1420
       Function: ai_chat_ui_init
       Location: .../ai_chat_ui.c:150 (discriminator 1)

   === Stack Code Pointers (4 candidates) ===
     0x021d1414  →  ai_chat_ui_init
                 at .../ai_chat_ui.c:142
     0x021d9094  →  lv_obj_get_scrollbar_mode
                 at .../lv_obj_scroll.c:94
   ```

4. **Investigate the crash site** — open the indicated file:line in your editor. Common next steps:
   - Null pointer dereference: inspect the callers of the faulting function for missing NULL checks.
   - Stack overflow: check thread stack sizes (see `tuyaopen-thread-crash` skill).
   - Use `--nm` flag to print nearby symbol context for extra orientation.

## Platform detection

The script auto-detects the platform by scanning the dump text for register names
and firmware version strings:

| Platform | Detection signals |
|----------|------------------|
| T5AI (BK7258) | `Firmware name: app@cpu1`, `bk7258`, ARM Cortex-M register names |
| ESP32 / ESP32-S3 | `ESP-IDF`, `EPC1`, `EXCVADDR`, Xtensa register names |
| T2 / T3 / LN882H | ARM Cortex-M registers (PC, LR, XPSR), no T5/ESP32 hints |
| LINUX | x86 register names (RIP, RSP, etc.) |

Use `--platform <name>` to override if auto-detection is wrong.

## ELF discovery

The script searches in this order:

```
dist/*/debug/bk7258_ap/app.elf   ← T5AI CPU1 (app@cpu1 dump)
dist/*/debug/bk7258/app.elf      ← T5AI CPU0
dist/*/debug/*/app.elf           ← Any platform, single-CPU
dist/*/*.elf                     ← Single-CPU fallback
TuyaOpen/platform/*/build/**/*.elf
.build/bin/debug/*/app.elf
.build/bin/*.elf
```

The **newest** ELF matching the highest-priority path wins. Use `--elf <path>` to
specify explicitly if multiple ELFs exist (e.g. after builds for different targets).

**Important:** The ELF must match the flashed binary exactly. If you built after
the crash, rebuild the same commit or keep the old `dist/` output.

## Toolchain discovery

```
TuyaOpen/platform/tools/*/bin/arm-none-eabi-addr2line   ← preferred (ARM)
~/.espressif/tools/**/bin/xtensa-esp32s3-elf-addr2line  ← ESP32
$IDF_PATH/tools/**/xtensa-esp32*-elf-addr2line          ← ESP32 (IDF env)
/opt/esp/tools/**                                        ← ESP32 (system)
arm-none-eabi-addr2line (in PATH)                        ← system fallback
```

Use `--toolchain <path>` to override.

## Options reference

| Option | Default | Description |
|--------|---------|-------------|
| `--elf <path>` | auto | Path to debug ELF file |
| `--toolchain <path>` | auto | Path to `addr2line` binary |
| `--platform <name>` | auto | `t5ai`, `esp32`, `t2`, `t3`, `ln882h`, `linux` |
| `--nm` | off | Print nm symbol context (nearby functions) for each address |
| `--dump-only` | off | Only show parsed addresses, skip addr2line decode |

## Stack address filtering

Stack data lines (`addr: 0x...  data: 0x...`) are common in BK7258/ARM dumps.
The script only includes `data:` values as code-pointer candidates when they fall
within the same memory region as PC/LR (a ±2 MB window, or 2× the PC–LR gap).
This filters out obvious data values (NULL, small integers, heap pointers).

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `addr2line not found` | Toolchain not downloaded | Run `tos.py build` once to trigger toolchain download, or `--toolchain` |
| `ELF not found` | No debug ELF in `dist/` | Build with debug info (`tos.py build`); check `dist/*/debug/*/app.elf` |
| All addresses decode to `??` | ELF does not match flashed binary | Use the ELF from the same build that was flashed |
| `Firmware name: app@cpu0` but getting wrong decode | Wrong ELF core selected | Use `--elf dist/.../bk7258/app.elf` (CPU0) instead of `bk7258_ap` |
| ESP32 toolchain not found | ESP-IDF not installed | `pip install esptool` won't help; install ESP-IDF or use `--toolchain` |
| Stack addresses all `unknown` | Stack contains data values, not return addresses | Normal — the register PC/LR frames are the reliable ones |

## Related skills

- **`tuyaopen-thread-crash`** — thread stack overflow analysis (complements this skill).
- **`tuyaopen-flash-monitor`** — capture device logs over serial to feed into this skill.
- **`agent-hardware-debug-helper-tools`** — detached serial logging + port discovery.
- **`tuyaopen-build`** — rebuild with debug info if ELF is missing.
