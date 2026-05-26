# Board Code Layer Rules & Shared Drivers

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

## Board CMakeLists.txt Template

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

## Board Driver Functions

Key functions to implement (varies by platform):

| Function | Purpose | Required |
|----------|---------|----------|
| `app_audio_driver_init(name)` | Register audio codec driver | If audio used |
| `board_display_init()` | Initialize LCD hardware | ESP32 only |
| `board_display_get_panel_io_handle()` | Get LCD panel IO handle | ESP32 only |
| `board_display_get_panel_handle()` | Get LCD panel handle | ESP32 only |

T5AI boards do **not** need the `board_display_*` functions — their display goes through the `tkl_display` layer.
