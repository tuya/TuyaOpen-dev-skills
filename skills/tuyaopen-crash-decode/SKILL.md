---
name: tuyaopen-crash-decode
description: >-
  Decode a TuyaOpen firmware crash dump (PC, LR, stack pointers) to source
  file:line by invoking the right per-platform `addr2line` against the debug
  ELF. Use when the user pastes a panic log / hard-fault dump containing raw
  hex code addresses (e.g. "PC: 0x021d8e96"). Covers T5AI (BK7258, ARM
  Cortex-M), ESP32/S3 (Xtensa), T2, T3, LN882H — each ships its own toolchain
  inside the TuyaOpen tree.
  固件崩溃解码、panic、hard fault、PC/LR地址解析、addr2line。
license: Apache-2.0
compatibility:
  - TuyaOpen repository checked out with the matching commit/branch flashed to the device
  - Toolchain available (`tos.py build` once is enough — it auto-downloads the right toolchain)
---

# TuyaOpen Crash Decode

When firmware panics on a TuyaOpen device, the serial log dumps raw register
values (`PC`, `LR`, sometimes `EPC1/2/3` for Xtensa) plus stack frame snapshots.
These addresses point into the `.text` section of the flashed firmware — to
turn them into useful information you need the **debug ELF** produced by the
same build and a `*-addr2line` from the **same toolchain** that built it.

There is no shared Python wrapper. Just call the toolchain binary directly —
the path is fully determined by the platform and is sitting in the TuyaOpen
tree after the first `tos.py build`.

## 1. Identify the platform from the dump

| Dump signal | Platform | Toolchain prefix |
|---|---|---|
| `Firmware name: app@cpu0` or `app@cpu1`, `bk7258` in path | **T5AI** (dual-core ARM Cortex-M33) | `arm-none-eabi-` |
| `ESP-IDF`, `EPC1/2/3`, `EXCVADDR`, `Guru Meditation Error` | **ESP32 / ESP32-S3** (Xtensa) | `xtensa-esp32-elf-` or `xtensa-esp32s3-elf-` |
| Cortex-M registers (`PC`, `LR`, `xPSR`, `CFSR`), no `app@cpu` and no ESP-IDF | **T2 / T3 / LN882H** (single-core ARM Cortex-M) | `arm-none-eabi-` |
| `RIP`, `RSP` (x86) | **LINUX** (Ubuntu/Raspberry Pi) | system `addr2line` |

For T5AI dual-core: `app@cpu0` ↔ CP core ↔ `bk7258/app.elf`, `app@cpu1` ↔ AP core ↔ `bk7258_ap/app.elf`. Pick the matching one.

## 2. Locate `addr2line`

After `tos.py build` runs once for any platform, the matching toolchain lives under `TuyaOpen/platform/tools/`. Search order:

```bash
# ARM (T5AI, T2, T3, LN882H)
find TuyaOpen/platform/tools -name 'arm-none-eabi-addr2line' -executable | head -1
# Example: TuyaOpen/platform/tools/gcc-arm-none-eabi-10.3-2021.10/bin/arm-none-eabi-addr2line

# ESP32 / ESP32-S3 (Xtensa)
find TuyaOpen/platform/ESP32/esp-idf -name 'xtensa-esp32s3-elf-addr2line' 2>/dev/null | head -1
# Or, if ESP-IDF is installed system-wide:
find ~/.espressif/tools "$IDF_PATH/tools" /opt/esp/tools -name 'xtensa-esp32*-elf-addr2line' 2>/dev/null | head -1

# Linux / Ubuntu / Raspberry Pi
which addr2line
```

If `find` returns empty for an embedded platform, run `tos.py build` once to trigger the toolchain download. The same directory also contains `*-nm`, `*-objdump`, `*-readelf` — useful for the steps below.

## 3. Locate the debug ELF

Search order (highest priority first):

```bash
# T5AI (dual-core, two ELFs)
ls -t dist/*/debug/bk7258_ap/app.elf 2>/dev/null | head -1     # CPU1 / AP
ls -t dist/*/debug/bk7258/app.elf    2>/dev/null | head -1     # CPU0 / CP

# Single-CPU platforms (ESP32, T2, T3, LN882H)
ls -t dist/*/*/*.elf 2>/dev/null | head -3

# Build tree (if dist/ is empty / not regenerated yet)
find TuyaOpen/platform -type f -name '*.elf' -path '*/build/*' 2>/dev/null | head -3
ls -t .build/bin/debug/*/app.elf .build/bin/*.elf 2>/dev/null | head -3
```

**The ELF must match the flashed binary exactly.** If the user rebuilt after the panic, ask them to either re-flash + reproduce the panic, OR `git checkout` the exact commit they flashed and `tos.py clean -f && tos.py build` to regenerate the matching ELF.

## 4. Decode

Single command — `addr2line` in inline mode (`-i`), with function name (`-f`) and demangled C++ symbols (`-C`):

```bash
ADDR2LINE=TuyaOpen/platform/tools/gcc-arm-none-eabi-10.3-2021.10/bin/arm-none-eabi-addr2line
ELF=dist/MyProject_1.0.0/debug/bk7258_ap/app.elf

# Decode PC + LR
$ADDR2LINE -e $ELF -f -C -i 0x021d8e96 0x021d5863

# Decode the saved stack frame return addresses (skip non-code stack values)
$ADDR2LINE -e $ELF -f -C -i  \
   0x021d139d 0x021b838d 0x0219be41 0x0219c423 0x0219bfd1 0x021d10e3
```

Example real output (T5AI, DuckyClaw wechat UI null deref):

```
lv_obj_get_scrollbar_mode
TuyaOpen/src/liblvgl/v9/lvgl/src/core/lv_obj_scroll.c:94
lv_obj_get_scrollbar_area
TuyaOpen/src/liblvgl/v9/lvgl/src/core/lv_obj_scroll.c:453
lv_obj_remove_flag
TuyaOpen/src/liblvgl/v9/lvgl/src/core/lv_obj.c:159
```

That's it. PC was inside `lv_obj_get_scrollbar_mode`, called from `lv_obj_get_scrollbar_area`, called from `lv_obj_remove_flag`.

## 5. Extract addresses from the dump

Crash dumps have a specific layout per platform — when assisting a user, copy the dump verbatim and apply these rules:

- **PC / LR** (Cortex-M T5AI/T2/T3/LN882H): lines like
  ```
  pc x 0x21d8e96
  lr x 0x21d5863
  ```
  (sometimes `PC:` and `LR:` capitalized — both forms appear).

- **PC / EPC** (Xtensa ESP32): `PC : 0x420f3a11`, `EPC1 : 0x...`, etc.

- **Stack frame return addresses** (any platform): the dump prints lines like
  ```
  addr: 60fdfde0    data: 2801cc54
  addr: 60fdfde4    data: 00000000
  addr: 60fdfdb4    data: 021d5873   ← code pointer
  ```
  Filter `data:` values to keep only those in the same 16 MB region as PC/LR
  (looser: same upper byte). Drop NULL (`0x00000000`), small integers
  (`< 0x00010000`), and obvious stack/heap pointers (`0x3fc...`, `0x60f...`,
  `0x2801....` for T5 SRAM/PSRAM).

After filtering, batch all candidate code pointers into one `addr2line -i` call.

## 6. Get symbol context (optional)

If `addr2line` returns `??` for an address but you know the ELF matches, the
address may sit between functions (e.g. in a literal pool). Use the matching
`*-nm` to find the nearest symbol:

```bash
NM=TuyaOpen/platform/tools/gcc-arm-none-eabi-10.3-2021.10/bin/arm-none-eabi-nm
$NM --size-sort --print-size $ELF | awk -v a=0x021d8e96 'BEGIN{a=strtonum(a)} \
   { s=strtonum("0x"$1); if (a >= s && a < s + strtonum("0x"$2)) print }'
```

Or dump the disassembly around the address:

```bash
OBJDUMP=TuyaOpen/platform/tools/gcc-arm-none-eabi-10.3-2021.10/bin/arm-none-eabi-objdump
$OBJDUMP -d --start-address=0x021d8e80 --stop-address=0x021d8ec0 $ELF
```

## 7. Common gotchas

| Symptom | Likely cause | Fix |
|---|---|---|
| All addresses decode to `??` | ELF doesn't match flashed binary | Re-flash + reproduce, or `git checkout` to the matching commit and rebuild |
| Some addresses decode, some don't | Some `data:` values aren't return addresses (data on stack) | Expected — only PC/LR + filtered code pointers are reliable |
| `addr2line: command not found` | Toolchain not downloaded yet | Run `tos.py build` once for any board → toolchain downloads to `TuyaOpen/platform/tools/` |
| ESP32: `xtensa-esp32s3-elf-addr2line` missing | ESP-IDF not installed | Install ESP-IDF, source `export.sh`, or use the toolchain bundled in `TuyaOpen/platform/ESP32/` after first build |
| Wrong T5AI core decoded (results don't make sense) | Picked `bk7258/app.elf` for an `app@cpu1` dump | Use `bk7258_ap/app.elf` for cpu1, `bk7258/app.elf` for cpu0 |
| `??:0` for inlined function | `addr2line` resolved the outermost but missed inlined frames | Make sure `-i` flag is present (inline mode); also re-build with `-g` if missing |

## Related skills

- **`tuyaopen-build`** — rebuild firmware with debug info enabled.
- **`tuyaopen-flash-monitor`** — capture the device serial log that contains the crash dump.
- **`agent-hardware-debug-helper-tools`** — background serial logger; useful for grabbing the dump hands-off.
- **`tuyaopen-cli-debug`** — once the device is responsive again, inspect runtime state via CLI.
