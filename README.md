<div align="center">

# Haylou S30 Pro — Windows Desktop App 🎧

**Control ANC, Transparency, Game Mode and Anti-leak on your Haylou S30 Pro straight from Windows — no phone, no mobile app.**
Smart auto-switch, scene profiles, software EQ and media controls, all in one window.

🇧🇷 [Versão em português](#-portugu%C3%AAs) · 🇺🇸 English below

![Platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.10-3776AB?logo=python&logoColor=white)
![Bluetooth LE](https://img.shields.io/badge/Bluetooth-LE-0082FC?logo=bluetooth&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-22D67B)

<img src="docs/screenshot.png" alt="Haylou S30 Pro Windows app — ANC control, scene profiles, equalizer and media controls" width="340">

</div>

## Why this exists

The official **Haylou Sound** app is **mobile-only**. If you live on your PC, there was no way to switch noise-cancelling modes, toggle Game Mode, or even check the battery without picking up your phone.

This is an independent **Windows** app that talks to the **Haylou S30 Pro** directly over **Bluetooth Low Energy** — the same protocol the phone app uses, reverse-engineered for interoperability. One window, global hotkeys, your headphones under control from the desktop.

## Features

- 🎚️ **ANC / Transparency / Normal** — one click, or use global hotkeys from anywhere: `Ctrl+Alt+A` cycles, `Ctrl+Alt+1/2/0` jump straight to a mode, `Ctrl+Alt+G` toggles Game Mode
- 🎮 **Game Mode** (low latency) and **Anti-leak** toggles — straight to the hardware
- 🎯 **Scene profiles** — one click applies a combo: **Focus** (ANC + Vocal EQ), **Gaming** (Game Mode + Normal), **Music** (ANC), **Call** (Transparency + Vocal EQ)
- 🤖 **AUTO mode** — reads what you're doing (music → ANC, call → Transparency, game → Game Mode) and switches for you. Lock the mode anytime so AUTO stops touching it.
- 🧠 **Learns your habits, locally** — every manual choice is remembered (per app + time of day) so AUTO gets smarter. An **usage stats** screen shows what you use most. Stored only on your machine — nothing leaves the PC.
- 🔋 **Battery with low/critical alerts** and a **battery sparkline** (last hours), plus now-playing and media controls (play / pause / next / previous and volume)
- 🎛️ **Software Equalizer** (via [Equalizer APO](https://sourceforge.net/projects/equalizerapo/)) and **Spatial Sound** (Windows Sonic) — features the headphones don't have in hardware, supplied by the PC. The EQ applies to **all PC audio** and isn't saved on the device.
- 🔄 **Reliable connection** — reconnects on its own; a **Reconnect** button forces it. Remembers your last mode/EQ between sessions.
- 🌐 **English / Portuguese** — auto-detects your Windows language, switchable in one click
- 🪟 **System tray** with a color-coded current-mode icon (click it to cycle ANC, hover for battery), **minimize-to-tray on close**, **auto-start on boot** and **light / dark themes**
- 💎 Premium UI, fits in one window, ships ready to run — no Python install required

## Download

➡️ **[Download the latest release](../../releases/latest)** — unzip and run `Haylou S30 Pro.exe`. No installer, no dependencies.

> Requires Windows 10/11 with Bluetooth LE. First launch scans for your Haylou and remembers it.

**"Windows protected your PC"?** The build isn't code-signed (a signing cert costs money for a free project), so SmartScreen shows a warning. To run it: click **More info → Run anyway**. If you'd rather be sure, verify the download against the **SHA-256** published in the release notes:

```powershell
Get-FileHash "Haylou S30 Pro.exe" -Algorithm SHA256
```

Prefer not to trust a binary? [Build it yourself](#build-from-source) from source in one command.

## Supported devices

Built and tested on the **Haylou S30 Pro** (over-ear headphone). Over BLE the hardware exposes **ANC, Game Mode and Anti-leak**, which are controlled directly. **EQ and spatial audio are provided through Windows** (Equalizer APO + Windows Sonic) because the S30 Pro doesn't implement them in the chipset. The connection layer is config-driven, so other Haylou models can be added without touching the UI.

## How it works

The Haylou Sound app drives the headphones through a Bluetooth LE **GATT** service. The protocol lives in a native library, so it was decoded from **live BLE traffic** rather than the app's Java code.

- Service `0000cf00` · write `0000cf05` · notify `0000cf06`
- Command frame: `AA BB CC 80 08 <len> <sn> 02 <attr> <value> DD EE FF`
- **ANC** = attribute `0x04` → `0` Normal · `1` ANC · `2` Transparency
- Battery, run-info and per-feature state are read back over the notify characteristic

Full notes in [`docs/`](docs/PROTOCOLO-REAL-S30.md).

> ⚠️ The app only ever sends **confirmed-safe** commands. Blindly writing unsupported attributes can make the chipset misread the bytes (e.g. as a volume change). If you fork this, keep that in mind.

## Build from source

```bash
pip install -r requirements.txt
python app/haylou_flet.py

# package into a standalone app (Windows):
powershell -File app/build_exe.ps1
```

## Tech stack

Python · [Flet](https://flet.dev) (Flutter-powered UI) · [bleak](https://github.com/hbldh/bleak) (Bluetooth LE) · [pycaw](https://github.com/AndreMiras/pycaw) (volume) · WinRT (now-playing) · [pystray](https://github.com/moses-palmer/pystray) (tray) · [PyInstaller](https://pyinstaller.org) (packaging).

## Privacy

Local-first by design. The app has **no analytics, no telemetry, no account, no server**. Everything — earbud control, battery, EQ, themes, AUTO learning — runs fully offline. Usage patterns (which mode you pick, per app + time of day) are stored only in `%APPDATA%\haylou-win\` as plain counts — no window titles, no audio, no text.

## 💼 Custom apps on demand

I build **custom desktop, web and automation apps on demand** (reverse-engineering, hardware integrations, internal tools, AI). Need something like this for your product or company?

**📱 WhatsApp: [+55 15 99166-9729](https://wa.me/5515991669729)** — Igor Silveira

## Disclaimer

Independent, unofficial project. **Not affiliated with, endorsed by, or connected to Haylou or its manufacturer.** "Haylou" and "S30 Pro" are trademarks of their respective owners and are used here only to describe compatibility. Provided **as-is** for personal interoperability — use at your own risk.

## License

[MIT](LICENSE) © 2026 Igor Silveira

---

<a name="-português"></a>

# 🇧🇷 Português

**Controle ANC, Transparência, Game Mode e Anti-vazamento do seu Haylou S30 Pro direto do Windows — sem celular, sem app de telefone.**
Troca automática inteligente, perfis de cenário, equalizador por software e controles de mídia, tudo numa janela.

## Por que existe

O app oficial **Haylou Sound** é **só pra celular**. Quem vive no PC não tinha como trocar o modo de cancelamento de ruído, ligar o Game Mode ou nem ver a bateria sem pegar o telefone.

Este é um app **independente pra Windows** que fala direto com o **Haylou S30 Pro** por **Bluetooth Low Energy** — o mesmo protocolo do app do celular, reverso-engenheirado pra interoperabilidade.

## Funcionalidades

- 🎚️ **ANC / Transparência / Normal** — um clique, ou atalhos globais: `Ctrl+Alt+A` cicla, `Ctrl+Alt+1/2/0` vão direto num modo, `Ctrl+Alt+G` liga/desliga o Game Mode
- 🎮 **Game Mode** (baixa latência) e **Anti-vazamento** — direto no hardware
- 🎯 **Perfis de cenário** — um clique aplica um combo: **Foco** (ANC + EQ Vocal), **Jogo** (Game Mode + Normal), **Música** (ANC), **Call** (Transparência + EQ Vocal)
- 🤖 **Modo AUTO** — entende o que você está fazendo (música → ANC, call → Transparência, jogo → Game Mode) e troca sozinho. Trave o modo quando quiser que o AUTO pare de mexer.
- 🧠 **Aprende seus hábitos, localmente** — cada escolha manual é lembrada (por app + horário) e o AUTO fica mais esperto. Uma tela de **estatísticas** mostra o que você mais usa. Fica só na sua máquina — nada sai do PC.
- 🔋 **Bateria com alerta de baixa/crítica** e um **gráfico de bateria** (últimas horas), além de tocando-agora e controles de mídia
- 🎛️ **Equalizador por software** (via [Equalizer APO](https://sourceforge.net/projects/equalizerapo/)) e **Som Espacial** (Windows Sonic) — recursos que o fone não tem no hardware, fornecidos pelo PC
- 🔄 **Conexão confiável** — reconecta sozinho; um botão **Reconectar** força. Lembra o último modo/EQ entre sessões.
- 🌐 **Português / Inglês** — detecta o idioma do Windows, troca em um clique
- 🪟 **Bandeja do sistema** com ícone colorido do modo (clique pra ciclar o ANC, passe o mouse pra ver a bateria), **minimiza pra bandeja ao fechar**, **abre no boot** e **tema claro / escuro**

## Download

➡️ **[Baixe a última versão](../../releases/latest)** — descompacte e rode `Haylou S30 Pro.exe`. Sem instalador, sem dependências.

> Requer Windows 10/11 com Bluetooth LE. Na primeira vez ele procura seu Haylou e lembra dele.

**"O Windows protegeu o seu PC"?** O app não é assinado (certificado custa caro pra um projeto grátis), então o SmartScreen avisa. Pra rodar: **Mais informações → Executar assim mesmo**.

## 💼 Aplicativos sob encomenda

Eu desenvolvo **apps desktop, web e automações sob encomenda** (engenharia reversa, integração com hardware, ferramentas internas, IA). Precisa de algo assim pro seu produto ou empresa?

**📱 WhatsApp: [+55 15 99166-9729](https://wa.me/5515991669729)** — Igor Silveira

## Aviso

Projeto independente e não-oficial. **Sem afiliação, endosso ou conexão com a Haylou ou seu fabricante.** "Haylou" e "S30 Pro" são marcas dos respectivos donos, usadas aqui só pra descrever compatibilidade. Fornecido **como está**, pra interoperabilidade pessoal — use por sua conta e risco.

---

<sub>Keywords: Haylou S30 Pro Windows app · controlar Haylou ANC no PC · Haylou desktop app · Haylou noise cancelling Windows · Haylou S30 Pro PC software · app fone Bluetooth Windows · apps sob encomenda · custom Windows apps developer.</sub>
