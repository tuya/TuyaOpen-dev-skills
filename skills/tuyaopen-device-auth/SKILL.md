---
name: tuyaopen-device-auth
description: >-
  Configure device authorization credentials (UUID, AuthKey, PID) and network
  provisioning for TuyaOpen devices. Use when the user mentions device auth,
  authorization, UUID, AuthKey, tuya_config.h, provisioning, pairing, or
  cloud connection. 设备授权、授权码、配网、UUID、AuthKey、云连接。
license: Apache-2.0
compatibility:
  - TuyaOpen environment activated (export.sh)
  - Tuya IoT Platform account (platform.tuya.com) for credentials
---

# TuyaOpen Device Authorization & Provisioning

Docs: <https://tuyaopen.ai/docs/quick-start/equipment-authorization>

## Authorization Overview

TuyaOpen devices need three credentials to connect to the Tuya cloud:

| Credential | Macro | Purpose |
|-----------|-------|---------|
| Product ID (PID) | `TUYA_PRODUCT_ID` | Identifies the product type on the Tuya IoT platform |
| UUID | `TUYA_OPENSDK_UUID` | Unique device identifier |
| AuthKey | `TUYA_OPENSDK_AUTHKEY` | Device authentication key (paired with UUID) |

### Credential Resolution Priority

The SDK resolves credentials in this order (first success wins):

1. **KV storage** — previously written via CLI `auth` command (keys: `UUID_TUYAOPEN` / `AUTHKEY_TUYAOPEN`)
2. **OTP / module flash** — `tuya_iot_license_read()` reads from hardware (pre-burned modules)
3. **Source code macros** — `TUYA_OPENSDK_UUID` / `TUYA_OPENSDK_AUTHKEY` in `tuya_config.h`

If none succeed, the device cannot connect to the cloud.

## Configuring tuya_config.h

Each application has a `tuya_config.h` (in `include/` or `src/`). Edit it with your credentials:

```c
#define TUYA_PRODUCT_ID      "xxxxxxxxxxxxxxxx"
#define TUYA_OPENSDK_UUID    "uuidxxxxxxxxxxxxxxxx"
#define TUYA_OPENSDK_AUTHKEY "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Optional for AP provisioning with QR code:

```c
#define TUYA_NETCFG_PINCODE  "12345678"
```

**File locations** (vary by project):
- `apps/tuya_cloud/switch_demo/src/tuya_config.h`
- `apps/tuya.ai/your_chat_bot/include/tuya_config.h`
- `apps/tuya_cloud/weather_get_demo/include/tuya_config.h`

> Note: some README files reference `TUYA_DEVICE_UUID` / `TUYA_DEVICE_AUTHKEY` — these are outdated names. The actual macros used in source code are `TUYA_OPENSDK_UUID` / `TUYA_OPENSDK_AUTHKEY`.

## Getting Credentials

### Product ID (PID)

1. Log in to [Tuya IoT Platform](https://platform.tuya.com).
2. Create a product matching your device type.
3. Copy the PID from the product page.

### UUID + AuthKey

Three ways to obtain:

1. **Pre-burned modules** — some Tuya modules come with credentials in OTP; no manual config needed.
2. **Purchase from Tuya platform** — visit <https://platform.tuya.com/purchase/index?type=6> to buy TuyaOpen-specific authorization codes.
3. **Free developer codes** — Tuya periodically offers free authorization codes for developers.

> Important: only **TuyaOpen-specific** authorization codes work. Standard Tuya module authorization codes are **not compatible**.

## Writing Auth via Serial & Network Provisioning

For CLI-based serial authorization (port selection, baud rates, commands), provisioning modes (BLE / AP), and the full provisioning flow, see `references/PROVISIONING.md`.

### Serial port discovery (agents)

Before interactive auth over UART, resolve the correct COM/tty device:

- Use skill **`agent-hardware-debug-helper-tools`**: run **`agent_target_tool.py`** from **`.agents/skills/agent-hardware-debug-helper-tools/agent_target_tool.py`** (paths relative to **TuyaOpen repo root**). It finds the repo by locating **`tos.py`**, then **`list-devices`** / **`pick-port`** with **VID `0x1a86`** / **PID `0x55d2`** for the default T5 USB–UART (dual-serial boards expose two interfaces — flash/auth often uses the **lower** enumerated port, monitor/log the **higher**; see **`tuyaopen-flash-monitor`**).
- Pass the chosen port to **`tos.py monitor`** / tyutool flows as documented in provisioning, or use **`agent_target_tool.py monitor --project-dir <app>`** for a consistent wrapper.
- To capture logs during provisioning without blocking the agent, use **`service start --detach`**, **`service tail`**, and **`logs latest`**; use **`debug-session run`** when a **clean reboot log** is needed first.

## Agent Strategy

### When generating or modifying tuya_config.h

1. **Always use placeholder values** in generated code:
   ```c
   #define TUYA_PRODUCT_ID      "your_product_id_here"
   #define TUYA_OPENSDK_UUID    "your_uuid_here"
   #define TUYA_OPENSDK_AUTHKEY "your_authkey_here"
   ```
2. **Warn the user** if credentials appear to be placeholders when they attempt to build/flash for cloud testing.
3. **Never log, commit, or display** real UUID/AuthKey values in output, comments, or commit messages.
4. If the user provides real credentials, write them only to `tuya_config.h` and remind them not to commit the file with real values.

### Detecting placeholder values

Placeholder patterns to check: values containing `your_`, `xxx`, `here`, empty strings, or strings shorter than expected length (UUID ~20 chars, AuthKey ~32 chars).
