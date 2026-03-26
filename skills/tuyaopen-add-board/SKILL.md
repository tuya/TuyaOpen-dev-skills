---
name: tuyaopen-add-board
description: >-
  Add new board (BSP) support to TuyaOpen, including board directory structure,
  Kconfig, drivers, and config files. Use when the user mentions adding a
  board, new board, BSP, board support, hardware adaptation, or tos.py new
  board. 添加开发板、板级适配、新增BSP、硬件适配。
license: Apache-2.0
compatibility:
  - TuyaOpen environment activated (export.sh)
  - Supported platform (T5AI, ESP32, LINUX, T2, T3, LN882H, BK7231X)
---

# TuyaOpen: Adding a New Board

Reference: `boards/add_new_board.md`

## Supported Platforms

| Platform | Chips |
|----------|-------|
| T5AI | T5AI series |
| ESP32 | ESP32, ESP32-S3, ESP32-C3, ESP32-C6 |
| LINUX | Ubuntu, Raspberry Pi, DshanPi |
| T2 | T2-U |
| T3 | T3 LCD Devkit |
| LN882H | LN882H, EWT103-W15 |
| BK7231X | BK7231X |

## Board Directory Structure

Create `boards/<PLATFORM>/<BOARD_NAME>/` with these files:

```
boards/<PLATFORM>/<BOARD_NAME>/
├── CMakeLists.txt       # Build config (usually no modification needed)
├── Kconfig              # Board selection and feature toggles
├── board_com_api.h      # Board-level API declarations
├── board_config.h       # Hardware pin/peripheral configuration
└── <board_name>.c       # Board init implementation
```

## Step-by-Step

### 1. Copy from an existing board

Pick a board on the same platform as a starting point:

```bash
cp -r boards/ESP32/DNESP32S3 boards/ESP32/MY_NEW_BOARD
```

### 2. Edit Kconfig

Set the chip and board identifiers. The `BOARD_CHOICE` value **must match** the directory name exactly (case-sensitive):

```kconfig
config CHIP_CHOICE
    string
    default "esp32s3"

config BOARD_CHOICE
    string
    default "MY_NEW_BOARD"

config BOARD_CONFIG
    bool
    default y
    select ENABLE_AUDIO
    select ENABLE_ESP_DISPLAY
```

### 3. Register in platform Kconfig

Add your board as an option in `boards/<PLATFORM>/Kconfig` so it appears in `config choice`.

### 4. Edit board_config.h

Define hardware-specific constants (display type, I/O expander, pin mappings, etc.):

```c
#define BOARD_DISPLAY_TYPE   DISPLAY_TYPE_LCD_SH8601
#define BOARD_IO_EXPANDER_TYPE IO_EXPANDER_TYPE_TCA9554
```

### 5. Implement board driver

Implement the board-specific init functions in `<board_name>.c`. For the list of required driver functions per platform and the standard CMakeLists.txt template, see `references/BOARD_LAYERS.md`.

### 6. Create a project config (optional)

For app-specific projects, create a config file in the project's `config/` directory:

```bash
cp apps/tuya.ai/your_chat_bot/config/TUYA_T5AI_EVB.config \
   apps/tuya.ai/your_chat_bot/config/MY_NEW_BOARD.config
```

### 7. Build and verify

```bash
cd apps/tuya.ai/your_chat_bot    # or your target project
tos.py config choice              # select your new board
tos.py build
```

## Code Layer Rules & Shared Drivers

For the dependency layer diagram (platform → src → boards/common → boards/BOARD → apps), existing ESP32 shared drivers (audio, LCD, touch, IO expander, LED), and the board CMakeLists.txt template, see `references/BOARD_LAYERS.md`.
