---
name: tuyaopen-add-board
description: >-
  Add new board (BSP) support to TuyaOpen, including board directory structure,
  Kconfig, drivers, and config files. Use when the user mentions adding a
  board, new board, BSP, board support, hardware adaptation, or tos.py new
  board. 添加开发板、板级适配、新增BSP、硬件适配。
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

### 5. Implement board driver (<board_name>.c)

Key functions to implement (varies by platform):

| Function | Purpose | Required |
|----------|---------|----------|
| `app_audio_driver_init(name)` | Register audio codec driver | If audio used |
| `board_display_init()` | Initialize LCD hardware | ESP32 only |
| `board_display_get_panel_io_handle()` | Get LCD panel IO handle | ESP32 only |
| `board_display_get_panel_handle()` | Get LCD panel handle | ESP32 only |

T5AI boards do **not** need the `board_display_*` functions — their display goes through the `tkl_display` layer.

### 6. CMakeLists.txt (usually unchanged)

The standard board CMakeLists.txt collects `.c` sources, exposes public headers, and registers itself as a component:

```cmake
set(MODULE_PATH ${CMAKE_CURRENT_LIST_DIR})
get_filename_component(MODULE_NAME ${MODULE_PATH} NAME)
aux_source_directory(${MODULE_PATH} LIB_SRCS)
set(LIB_PUBLIC_INC ${MODULE_PATH})

add_library(${MODULE_NAME})
target_sources(${MODULE_NAME} PRIVATE ${LIB_SRCS})
target_include_directories(${MODULE_NAME} PRIVATE ${LIB_PRIVATE_INC} PUBLIC ${LIB_PUBLIC_INC})

list(APPEND COMPONENT_LIBS ${MODULE_NAME})
set(COMPONENT_LIBS "${COMPONENT_LIBS}" PARENT_SCOPE)
list(APPEND COMPONENT_PUBINC ${LIB_PUBLIC_INC})
set(COMPONENT_PUBINC "${COMPONENT_PUBINC}" PARENT_SCOPE)
```

### 7. Create a project config (optional)

For app-specific projects, create a config file in the project's `config/` directory:

```bash
# e.g. for your_chat_bot
cp apps/tuya.ai/your_chat_bot/config/TUYA_T5AI_EVB.config \
   apps/tuya.ai/your_chat_bot/config/MY_NEW_BOARD.config
# Then edit to match your board's Kconfig selections
```

### 8. Build and verify

```bash
cd apps/tuya.ai/your_chat_bot    # or your target project
tos.py config choice              # select your new board
tos.py build
```

## Code Layer Rules

Understanding the dependency layers helps avoid build errors:

```
platform/  ← chip vendor SDK + tkl adaptation layer
    ↑ (tkl can call vendor SDK)
src/       ← TuyaOpen SDK components (tal_*, lib*)
    ↑ (src can call tkl, NOT vendor SDK)
boards/<PLATFORM>/common/  ← shared drivers for a platform
    ↑ (can call tkl + vendor SDK)
boards/<PLATFORM>/<BOARD>/  ← board-specific code
    ↑ (can call tkl + src + boards/common, NOT vendor SDK directly)
apps/      ← application code
    ↑ (can call tkl + src, NOT vendor SDK)
```

## Existing Shared Drivers (ESP32)

Before writing new drivers, check `boards/ESP32/common/`:

| Directory | Available drivers |
|-----------|------------------|
| `common/audio/` | no-codec, ES8311, ES8388, ES8389, ATK no-codec |
| `common/lcd/` | SSD1306 OLED, SH8601, ST7789 (80-bus), ST7789 (SPI) |
| `common/display/` | LVGL port (lv_port_disp, lv_port_indev, lv_vendor) |
| `common/touch/` | FT5x06 |
| `common/io_expander/` | TCA9554, XL9555 |
| `common/led/` | WS2812 (ESP RMT) |
