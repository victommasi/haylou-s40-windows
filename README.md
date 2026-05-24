<div align="center">

# Haylou S30 Pro — Windows Desktop App 🎧

**Control ANC, Transparency, Game Mode and Anti-leak on your Haylou S30 Pro straight from Windows — no phone, no mobile app.**
Plus an on-device AI that switches modes automatically based on what you're doing.

![Platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.10-3776AB?logo=python&logoColor=white)
![Bluetooth LE](https://img.shields.io/badge/Bluetooth-LE-0082FC?logo=bluetooth&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-22D67B)

<img src="docs/screenshot.png" alt="Haylou S30 Pro Windows app — ANC control, equalizer and media controls" width="330">

</div>

## Why this exists

The official **Haylou Sound** app is **mobile-only**. If you live on your PC, there was no way to switch noise-cancelling modes, toggle Game Mode, or even check the battery without picking up your phone.

This is an independent **Windows** app that talks to the **Haylou S30 Pro** directly over **Bluetooth Low Energy** — the same protocol the phone app uses, reverse-engineered for interoperability. One window, one hotkey, your earbuds under control from the desktop.

## Features

- 🎚️ **ANC / Transparency / Normal** — one click, or cycle from anywhere with a global hotkey (`Ctrl+Alt+A`)
- 🎮 **Game Mode** (low latency) and **Anti-leak** toggles — straight to the hardware
- 🤖 **AI auto-switch** — reads what you're doing (music → ANC, call → Transparency, game → Game Mode) and switches for you. One click on the 🔒 locks the mode so the AI stops touching it.
- 🧠 **Learns your habits, locally** — every manual choice is remembered (per app + time of day) so AUTO gets smarter over time. Stored only on your machine — nothing leaves the PC.
- 💬 **Natural-language command bar** *(optional)* — type "focus mode", "sleep in 20 min", "warmer sound" and it does it. Powered by Google Gemini's free tier with **your own key** (no key is bundled). Only the text you type is sent; everything else stays local.
- 🔋 **Battery, now-playing and media controls** — play / pause / next / previous and volume, with a live equalizer animation
- 🎛️ **Software Equalizer** (via [Equalizer APO](https://sourceforge.net/projects/equalizerapo/)) and **Spatial Sound** (Windows Sonic) — features the earbuds don't have in hardware, supplied by the PC. The EQ applies to **all PC audio**, not just the earbuds, and isn't saved on the device.
- 🪟 **System tray** with a color-coded current-mode icon, **auto-start on boot**, and **low-battery notifications**
- 💎 Premium UI with **light / dark themes** (instant toggle), fits in one compact window, ships as a **single `.exe`** — no Python install required

## Download

➡️ **[Download the latest `.exe`](../../releases/latest)** — just run it. No installer, no dependencies.

> Requires Windows 10/11 with Bluetooth LE. First launch scans for your Haylou earbuds and remembers them.

**"Windows protected your PC"?** The `.exe` isn't code-signed (a signing cert costs money for a free project), so SmartScreen shows a warning. To run it: click **More info → Run anyway**. If you'd rather be sure, verify the download against the **SHA-256** published in the release notes:

```powershell
Get-FileHash "Haylou S30 Pro.exe" -Algorithm SHA256
```

Prefer not to trust a binary? [Build it yourself](#build-from-source) from source in one command.

## Supported devices

Built and tested on the **Haylou S30 Pro**. Over BLE the hardware exposes **ANC, Game Mode and Anti-leak**, which are controlled directly. **EQ and spatial audio are provided through Windows** (Equalizer APO + Windows Sonic) because the S30 Pro doesn't implement them in the chipset. The connection layer is config-driven, so other Haylou models can be added without touching the UI.

## How it works

The Haylou Sound app drives the earbuds through a Bluetooth LE **GATT** service. The protocol lives in a native library, so it was decoded from **live BLE traffic** rather than the app's Java code.

- Service `0000cf00` · write `0000cf05` · notify `0000cf06`
- Command frame: `AA BB CC 80 08 <len> <sn> 02 <attr> <value> DD EE FF`
- **ANC** = attribute `0x04` → `0` Normal · `1` ANC · `2` Transparency
- Battery, run-info and per-feature state are read back over the notify characteristic

Full notes in [`docs/`](docs/PROTOCOLO-REAL-S30.md).

> ⚠️ The app only ever sends **confirmed-safe** commands. Blindly writing unsupported attributes can make the chipset misread the bytes (e.g. as a volume change). If you fork this, keep that in mind.

## Build from source

```bash
pip install flet bleak pycaw winrt pystray pillow keyboard comtypes win10toast-click
python app/haylou_flet.py

# package into a standalone .exe (Windows):
powershell -File app/build_exe.ps1
```

## Tech stack

Python · [Flet](https://flet.dev) (Flutter-powered UI) · [bleak](https://github.com/hbldh/bleak) (Bluetooth LE) · [pycaw](https://github.com/AndreMiras/pycaw) (volume) · WinRT (now-playing) · [pystray](https://github.com/moses-palmer/pystray) (tray) · [PyInstaller](https://pyinstaller.org) (packaging).

## Privacy

Local-first by design. The app has **no analytics, no telemetry, no account, no server**.

- **Earbud control, battery, EQ, themes** — fully offline.
- **AUTO learning** — usage patterns (which mode you pick, per app + time of day) are stored only in `%APPDATA%\haylou-win\usage.json` on your machine. Counts only — no window titles, no audio, no text.
- **Command bar (optional AI)** — the **only** thing that ever leaves your PC, and only when you use it: the sentence you type is sent to Google Gemini to interpret. Your key stays in your local config and is never bundled in the build.

## Disclaimer

Independent, unofficial project. **Not affiliated with, endorsed by, or connected to Haylou or its manufacturer.** "Haylou" and "S30 Pro" are trademarks of their respective owners and are used here only to describe compatibility. Provided **as-is** for personal interoperability — use at your own risk.

## License

[MIT](LICENSE) © 2026 Igor Silveira

---

<sub>Keywords: Haylou S30 Pro Windows app · control Haylou ANC on PC · Haylou desktop app · Haylou noise cancelling on Windows · Haylou S30 Pro PC software · Bluetooth headphones control Windows · Haylou transparency mode PC.</sub>
