# Quick TuyaOpen environment verification for PowerShell.
# Returns exit code 0 if all checks pass, 1 otherwise.

$ok = $true
Write-Host "=== TuyaOpen Environment Check ==="

if ($env:OPEN_SDK_ROOT) {
    Write-Host "[OK]   OPEN_SDK_ROOT=$($env:OPEN_SDK_ROOT)"
} else {
    Write-Host "[FAIL] OPEN_SDK_ROOT not set (run: .\export.ps1)"
    $ok = $false
}

if ($env:VIRTUAL_ENV) {
    Write-Host "[OK]   Python venv activated ($($env:VIRTUAL_ENV))"
} else {
    Write-Host "[FAIL] Python venv not activated (run: .\export.ps1)"
    $ok = $false
}

foreach ($tool in @("tos.py", "git", "cmake", "ninja", "python")) {
    if (Get-Command $tool -ErrorAction SilentlyContinue) {
        Write-Host "[OK]   $tool available"
    } else {
        Write-Host "[FAIL] $tool not found"
        $ok = $false
    }
}

Write-Host ""
if ($env:OPEN_SDK_ROOT) {
    Write-Host "--- tos.py version ---"
    & tos.py version 2>&1
    Write-Host ""
}

if ($ok) {
    Write-Host "RESULT: All checks passed."
    exit 0
} else {
    Write-Host "RESULT: Some checks FAILED. Run '.\export.ps1' from the repo root."
    exit 1
}
