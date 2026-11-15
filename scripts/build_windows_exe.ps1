# Package the Wi-Fi setup wizard as a single Windows .exe (no administrator rights needed).
#   powershell -ExecutionPolicy Bypass -File scripts\build_windows_exe.ps1
# Requires Python 3 (with tkinter) on PATH. Output: dist\RowentaWifiSetup.exe
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".build-venv"
$tool = Join-Path $root "custom_components\rowenta_pure_air\tools\rowenta_wifi_setup.py"

if (-not (Test-Path $venv)) { python -m venv $venv }
& "$venv\Scripts\python.exe" -m pip install --quiet --upgrade pyinstaller

& "$venv\Scripts\pyinstaller.exe" --noconfirm --clean --onefile --windowed `
    --name RowentaWifiSetup `
    --icon (Join-Path $root "assets\icon.ico") `
    --distpath (Join-Path $root "dist") `
    --workpath (Join-Path $root "build") `
    --specpath (Join-Path $root "build") `
    $tool
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path $root "dist\RowentaWifiSetup.exe"
$hash = (Get-FileHash $exe -Algorithm SHA256).Hash
$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "`nBuilt: $exe ($size MB)"
Write-Host "SHA-256:  $hash"
Write-Host "Publish this hash next to the .exe so anyone can verify it has not been altered."
