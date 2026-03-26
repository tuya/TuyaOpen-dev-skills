# TuyaOpen Error Codes & CLI Reference

## Common Error Codes

| Code | Name | Value | Typical cause |
|------|------|-------|---------------|
| `OPRT_OK` | Success | 0 | — |
| `OPRT_COM_ERROR` | General error | -1 | Catch-all failure |
| `OPRT_INVALID_PARM` | Invalid parameter | -2 | NULL pointer or out-of-range argument |
| `OPRT_MALLOC_FAILED` | Allocation failed | -3 | Out of memory |
| `OPRT_NOT_SUPPORTED` | Not supported | -4 | Feature disabled or platform mismatch |
| `OPRT_NETWORK_ERROR` | Network error | -5 | WiFi disconnected or DNS failure |
| `OPRT_NOT_FOUND` | Not found | -6 | Missing resource, file, or config |

Full error code definitions: `src/common/include/tuya_error_code.h`

## CLI System Details

### Overview

TuyaOpen includes a built-in CLI system (`tal_cli`) accessible via the debug UART. The CLI prompt is `tuya> `.

### Using CLI via Monitor

1. Start monitor: `tos.py monitor` (use the correct baud rate for your chip — see skill `tuyaopen-flash-monitor`)
2. Type commands at the `tuya> ` prompt
3. CLI supports tab completion and command history (up/down keys)

### Built-in Commands

| Command | Description | Requires |
|---------|-------------|----------|
| `help` | List all registered commands | `tal_cli_init()` |
| `auth <uuid> <authkey>` | Write device credentials | `tuya_authorize_init()` |
| `auth-read` | Read stored credentials | `tuya_authorize_init()` |
| `auth-reset` | Clear stored credentials | `tuya_authorize_init()` |

### Registering Custom CLI Commands

Applications can register custom test commands:

```c
static void my_test_cmd(int argc, char *argv[]) {
    PR_DEBUG("test command executed, argc=%d", argc);
}

static const cli_cmd_t my_cmds[] = {
    { .name = "mytest", .help = "run my test", .func = my_test_cmd },
};

tal_cli_cmd_register(my_cmds, sizeof(my_cmds) / sizeof(my_cmds[0]));
```

## Batch Testing

### Build All Configs

```bash
tos.py dev bac                    # build every config in the project
tos.py dev bac --dist ./output    # save binaries to output dir
tos.py dev bac -o ./logs          # save build logs
```

Useful for regression testing across all supported board configurations.
