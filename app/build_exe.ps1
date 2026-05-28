# Packages Haylou S30 Pro into a single standalone .exe (no terminal, no Python needed).
#
#   powershell -ExecutionPolicy Bypass -File build_exe.ps1
#   powershell -File build_exe.ps1 -Python "C:\path\to\python.exe"   # override interpreter
#
# Notes that took a few failed builds to learn:
#  * Build OUTSIDE the project dir (workpath in %TEMP%). An antivirus/indexer touching the
#    in-project `build\` folder mid-build causes `FileNotFoundError: base_library.zip`.
#  * Pass --add-data sources as ABSOLUTE paths, otherwise they resolve relative to the
#    spec file (which lives in the temp workpath) and PyInstaller can't find the assets.
#  * Use the Python that actually has the deps installed (flet/bleak/pycaw/winrt/...),
#    not a bare `python` stub on PATH.
param([string]$Python = "")

$ErrorActionPreference = 'Stop'
$app  = $PSScriptRoot
$work = Join-Path $env:TEMP 'haylou_pyi'

if (-not $Python) {
    $local310 = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe'
    if (Test-Path $local310) { $Python = $local310 } else { $Python = 'python' }
}
Write-Host "Python:  $Python"
Write-Host "Workdir: $work"

Write-Host "Cleaning previous build..." -ForegroundColor DarkGray
Remove-Item -Recurse -Force "$app\build", "$app\dist" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $work | Out-Null

# --onedir (NÃO --onefile): o exe + DLLs ficam numa pasta fixa. Sem descompactar no
# temp (_MEI) a cada abertura → acaba o erro "Failed to load python310.dll" e o ícone
# da taskbar fica estável. Distribui zipando a pasta dist\Haylou S30 Pro\.
Write-Host "Packaging with PyInstaller (--onedir, takes a few minutes)..." -ForegroundColor Yellow
& $Python -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name "Haylou S30 Pro" `
    --workpath  $work `
    --specpath  $work `
    --distpath  "$app\dist" `
    --icon      "$app\assets\s30.ico" `
    --add-data  "$app\assets\s30.png;assets" `
    --add-data  "$app\assets\s30.ico;assets" `
    --collect-all "flet" `
    --collect-all "flet_desktop" `
    --collect-all "winrt" `
    --collect-submodules "bleak" `
    --hidden-import "winrt.windows.media.control" `
    --hidden-import "winrt.windows.foundation" `
    --hidden-import "winrt.windows.devices.bluetooth" `
    --hidden-import "winrt.windows.devices.bluetooth.genericattributeprofile" `
    --hidden-import "winrt.windows.devices.bluetooth.advertisement" `
    --hidden-import "comtypes" `
    --hidden-import "pycaw.pycaw" `
    --hidden-import "pystray._win32" `
    --hidden-import "PIL.ImageFont" `
    --hidden-import "keyboard" `
    "$app\haylou_flet.py"

Write-Host ""
# no onedir o exe fica em dist\Haylou S30 Pro\Haylou S30 Pro.exe
$exe = "$app\dist\Haylou S30 Pro\Haylou S30 Pro.exe"
if (Test-Path $exe) {
    $folder = "$app\dist\Haylou S30 Pro"
    $sz = [math]::Round(((Get-ChildItem $folder -Recurse | Measure-Object Length -Sum).Sum) / 1MB, 1)
    Write-Host "APP created: $exe (pasta ~$sz MB)" -ForegroundColor Green
} else {
    Write-Host "FAILED - exe not generated, see the PyInstaller output above" -ForegroundColor Red
    exit 1
}
