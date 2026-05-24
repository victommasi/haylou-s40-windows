# Empacota o Haylou S30 Pro num app standalone (sem terminal, sem Python visivel).
# Usa o Python310 (onde flet/bleak/pycaw/winrt estao instalados), nao o 'python' do PATH.
# MODO --onedir: pasta com o .exe + _internal/. Mais robusto que --onefile (que crasha
# no PKG comprimindo o binario gigante do Flet). No fim zipa pra compartilhar.
$ErrorActionPreference = 'Continue'
Set-Location 'C:\Projetos\haylou-win\app'

$py = 'C:\Users\Igor Silveira\AppData\Local\Programs\Python\Python310\python.exe'

Write-Host "Limpando build anterior..." -ForegroundColor DarkGray
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Remove-Item -Force '*.spec' -ErrorAction SilentlyContinue

$a = @('-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','HaylouS30Pro',
  '--icon','assets\s30.ico','--add-data','assets\s30.png;assets','--add-data','assets\s30.ico;assets',
  '--collect-all','flet','--collect-all','flet_desktop','--collect-all','winrt',
  '--hidden-import','winrt.windows.media.control','--hidden-import','winrt.windows.foundation',
  '--hidden-import','winrt.windows.devices.bluetooth',
  '--hidden-import','winrt.windows.devices.bluetooth.genericattributeprofile',
  '--hidden-import','winrt.windows.devices.bluetooth.advertisement','--hidden-import','comtypes',
  '--hidden-import','pycaw.pycaw','--hidden-import','pystray._win32','--hidden-import','PIL.ImageFont',
  '--hidden-import','keyboard','haylou_flet.py')

Write-Host "Empacotando com PyInstaller (--onedir, pode levar alguns minutos)..." -ForegroundColor Yellow
$p = Start-Process -FilePath $py -ArgumentList $a -WorkingDirectory 'C:\Projetos\haylou-win\app' `
     -RedirectStandardOutput 'build.out.log' -RedirectStandardError 'build.err.log' -NoNewWindow -Wait -PassThru
Write-Host "PyInstaller ExitCode: $($p.ExitCode)"

Write-Host ""
if (Test-Path 'dist\HaylouS30Pro\HaylouS30Pro.exe') {
    # nome bonito pro exe (onedir: o exe acha o _internal ao lado, pode renomear)
    Rename-Item 'dist\HaylouS30Pro\HaylouS30Pro.exe' 'Haylou S30 Pro.exe' -ErrorAction SilentlyContinue
    Rename-Item 'dist\HaylouS30Pro' 'Haylou S30 Pro' -ErrorAction SilentlyContinue
    $sz = [math]::Round(((Get-ChildItem 'dist\Haylou S30 Pro' -Recurse | Measure-Object Length -Sum).Sum)/1MB, 1)
    Write-Host "APP criado: dist\Haylou S30 Pro\Haylou S30 Pro.exe (pasta = $sz MB)" -ForegroundColor Green
    Write-Host "Zipando pra compartilhar..." -ForegroundColor Yellow
    Compress-Archive -Path 'dist\Haylou S30 Pro\*' -DestinationPath 'dist\Haylou S30 Pro.zip' -Force
    $zsz = [math]::Round((Get-Item 'dist\Haylou S30 Pro.zip').Length/1MB, 1)
    Write-Host "ZIP: dist\Haylou S30 Pro.zip ($zsz MB)" -ForegroundColor Green
} else {
    Write-Host "FALHOU - app nao gerado, ver build.err.log" -ForegroundColor Red
}
