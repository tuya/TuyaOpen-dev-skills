---
name: tuyaopen-device-auth
description: >-
  Configure device authorization credentials (UUID, AuthKey, PID) and network
  provisioning for TuyaOpen devices. Use when the user mentions device auth,
  authorization, UUID, AuthKey, tuya_config.h, provisioning, pairing, or
  cloud connection. 设备授权、授权码、配网、UUID、AuthKey、云连接。
---

# TuyaOpen Device Authorization & Provisioning

Docs: <https://tuyaopen.ai/zh/docs/quick-start/device-authorization>

## Authorization Overview

TuyaOpen devices need three credentials to connect to the Tuya cloud:

| Credential | Macro | Purpose |
|-----------|-------|---------|
| Product ID (PID) | `TUYA_PRODUCT_ID` | Identifies the product type on the Tuya IoT platform |
| UUID | `TUYA_OPENSDK_UUID` | Unique device identifier |
| AuthKey | `TUYA_OPENSDK_AUTHKEY` | Device authentication key (paired with UUID) |

### Credential resolution priority

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

## Writing Auth via Serial (CLI)

For devices with `tal_cli` enabled, you can write credentials at runtime via the serial console without recompiling.

### Which serial port to use

| Platform | Auth port | How to connect |
|----------|----------|----------------|
| LINUX (Ubuntu, etc.) | N/A — use monitor port | `tos.py monitor` (stdout, no physical serial) |
| T5AI, ESP32, T2, T3, etc. | **Flash/download port** (not monitor port!) | `tos.py monitor -p <flash_port> -b 115200` |

> For MCU platforms, authorization is done through the **flash port** (the same port used for `tos.py flash`), **not** the monitor/log port. The authorization baud rate is **115200** regardless of chip type.

### Steps

1. Build and flash the firmware.
2. Connect to the correct serial port at 115200 baud:
   - **LINUX**: `tos.py monitor` (uses stdout directly)
   - **MCU platforms**: `tos.py monitor -p <flash_port> -b 115200`
3. At the `tuya> ` prompt, use the `auth` command:

```
tuya> auth <UUID> <AUTHKEY>
```

### CLI auth commands

| Command | Description |
|---------|-------------|
| `auth <uuid> <authkey>` | Write new credentials to KV storage |
| `auth-read` | Read and display current stored credentials |
| `auth-reset` | Clear stored credentials |

### Authorization fails?

If the `tuya> ` prompt does not appear or the `auth` command is not recognized:

1. **Check baud rate**: authorization uses **115200**, not the chip's monitor baud rate.
2. **Check port**: MCU platforms use the **flash port**, not the monitor port.
3. **Check firmware**: `tuya_authorize_init()` must be called in the application code. Most cloud demo apps call it in `user_main()`. If missing, add it before `tuya_iot_init()`.
4. **Check CLI init**: `tal_cli_init()` must also be called to enable the CLI subsystem. Without it, there is no `tuya> ` prompt at all.

## Network Provisioning

After authorization, WiFi devices need network provisioning to receive the router SSID/password.

### Provisioning modes

| Mode | Kconfig flag | How it works |
|------|-------------|--------------|
| BLE | `NETCFG_TUYA_BLE` | Phone sends WiFi credentials via BLE; most common |
| AP | `NETCFG_TUYA_WIFI_AP` | Device creates a hotspot; phone connects and sends credentials |
| BLE + AP | Both flags | Supports both methods |

Applications configure this in their `user_main()`:

```c
netmgr_conn_set(NETCONN_WIFI, NETCONN_CMD_NETCFG,
    &(netcfg_args_t){ .type = NETCFG_TUYA_BLE | NETCFG_TUYA_WIFI_AP });
```

### PINCODE (AP mode)

If `TUYA_NETCFG_PINCODE` is defined, AP provisioning uses PBKDF2(pincode, uuid) to derive a TLS-PSK, enabling QR-code-based secure pairing. Without PINCODE, AP uses a different TLS+PSK protocol.

### Provisioning flow

1. Device starts in un-provisioned state (no saved WiFi credentials).
2. Device advertises via BLE and/or creates AP hotspot.
3. User opens Tuya Smart App / Smart Life App, scans for device.
4. App sends WiFi SSID + password + activation token.
5. Device connects to WiFi, activates with Tuya cloud.
6. `TUYA_EVENT_DIRECT_MQTT_CONNECTED` event fires — device is online.

### LINUX target

LINUX platform devices use the host's network directly — no provisioning needed. The device connects to the cloud immediately after `tuya_iot_start()`.

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
