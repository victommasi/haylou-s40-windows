# Cria um atalho .lnk pro app com AppUserModelID e ícone embutidos.
# Por que: o Flet desktop cria a janela via um flet.exe temporário, então fixar o app
# RODANDO fixa o processo errado (ícone do Flet). Fixando ESTE atalho, o Windows usa a
# AppID + ícone daqui — que batem com os que o app seta em runtime (set_app_user_model_id)
# → o ícone fixado fica correto e o clique abre o app certo.
param(
    [string]$ExePath = "",
    [string]$IcoPath = "",
    [string]$LnkPath = ""
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $ExePath) { $ExePath = Join-Path $PSScriptRoot "dist\Haylou S40\Haylou S40.exe" }
if (-not $IcoPath) { $IcoPath = Join-Path $PSScriptRoot "assets\s40.ico" }
if (-not $LnkPath) { $LnkPath = Join-Path (Split-Path $ExePath) "Haylou S40.lnk" }

$APPID = "RevoluteDigital.HaylouS40"  # tem que bater com set_app_user_model_id() no código

# 1) cria o atalho base
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($LnkPath)
$lnk.TargetPath = $ExePath
$lnk.WorkingDirectory = Split-Path $ExePath
if (Test-Path $IcoPath) { $lnk.IconLocation = "$IcoPath,0" }
$lnk.Description = "Haylou S40"
$lnk.Save()

# O AppUserModelID é setado pelo PRÓPRIO app em runtime (set_app_user_model_id),
# então o agrupamento/ícone na taskbar já usa a AppID correta. Este atalho aponta
# pro exe certo (não o flet temporário) e carrega o ícone embutido — fixar ELE
# (em vez do app rodando) resolve o "ícone foge / abre o flet".
Write-Host "Atalho criado: $LnkPath" -ForegroundColor Green
