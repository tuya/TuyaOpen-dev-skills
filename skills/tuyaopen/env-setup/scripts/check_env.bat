@echo off
:: Quick TuyaOpen environment verification for Windows CMD.
:: Returns 0 if all checks pass, 1 otherwise.
setlocal enabledelayedexpansion
set OK=0

echo === TuyaOpen Environment Check ===

if defined OPEN_SDK_ROOT (
    echo [OK]   OPEN_SDK_ROOT=%OPEN_SDK_ROOT%
) else (
    echo [FAIL] OPEN_SDK_ROOT not set (run: export.bat)
    set OK=1
)

if defined VIRTUAL_ENV (
    echo [OK]   Python venv activated (%VIRTUAL_ENV%)
) else (
    echo [FAIL] Python venv not activated (run: export.bat)
    set OK=1
)

where tos.py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK]   tos.py reachable
) else (
    echo [FAIL] tos.py not found
    set OK=1
)

for %%T in (git cmake ninja python) do (
    where %%T >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo [OK]   %%T available
    ) else (
        echo [FAIL] %%T not found
        set OK=1
    )
)

echo.
if defined OPEN_SDK_ROOT (
    echo --- tos.py version ---
    tos.py version 2>&1
    echo.
)

if %OK% NEQ 0 (
    echo RESULT: Some checks FAILED. Run 'export.bat' from the repo root.
    exit /b 1
) else (
    echo RESULT: All checks passed.
    exit /b 0
)
