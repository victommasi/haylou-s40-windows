"""
Integração com o sistema: tray icon, hotkey global, persistência, notificação, auto-start.
Mantém o app "sempre lá" — controle invisível do fone.
"""
import os
import json
import threading
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(os.environ.get("APPDATA", APP_DIR), "haylou-win", "config.json")
ICON_PATH = os.path.join(APP_DIR, "assets", "s30.png")

# ─── Persistência (lembra último estado/EQ) ───
def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg: dict):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

# ─── Notificação Windows (bateria baixa etc) ───
def notify(title: str, msg: str):
    """Notificação toast do Windows (best-effort, sem travar)."""
    def _do():
        try:
            from win10toast_click import ToastNotifier
            ToastNotifier().show_toast(title, msg, duration=5, threaded=True,
                                       icon_path=None)
        except Exception:
            # fallback: PowerShell balloon
            try:
                ps = (f'powershell -NoProfile -Command "'
                      f'[reflection.assembly]::loadwithpartialname(\'System.Windows.Forms\');'
                      f'$n=New-Object System.Windows.Forms.NotifyIcon;'
                      f'$n.Icon=[System.Drawing.SystemIcons]::Information;'
                      f'$n.Visible=$true;$n.ShowBalloonTip(5000,\'{title}\',\'{msg}\',\'Info\')"')
                os.system(ps)
            except Exception:
                pass
    threading.Thread(target=_do, daemon=True).start()

# ─── Hotkey global ───
def register_hotkey(combo: str, callback):
    """Registra hotkey global (ex: 'ctrl+alt+a'). Não-bloqueante."""
    try:
        import keyboard
        keyboard.add_hotkey(combo, callback)  # já roda em background, sem wait()
    except Exception:
        pass

# ─── System Tray ───
# cor (RGB) + letra por modo: Normal cinza, ANC vermelho, Transparência azul
TRAY_MODE = {
    0: ((100, 116, 139), "N"),
    1: ((255, 59, 92),   "A"),
    2: ((59, 130, 246),  "T"),
}
TRAY_MODE_NAMES = {0: "Normal", 1: "ANC", 2: "Transparência"}

def _mode_icon_img(mode: int):
    """Gera um ícone 64x64 com a cor do modo e a inicial no centro."""
    from PIL import Image, ImageDraw, ImageFont
    color, letter = TRAY_MODE.get(mode, ((255, 59, 92), "A"))
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], fill=color + (255,))
    try:
        font = ImageFont.truetype("segoeuib.ttf", 40)
    except Exception:
        font = ImageFont.load_default()
    try:
        bb = d.textbbox((0, 0), letter, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        d.text(((64 - tw) / 2 - bb[0], (64 - th) / 2 - bb[1]), letter,
               fill=(255, 255, 255, 255), font=font)
    except Exception:
        d.text((22, 14), letter, fill=(255, 255, 255, 255), font=font)
    return img

def make_tray(on_show, on_anc, on_transp, on_normal, on_quit, get_mode=lambda: 1):
    """Cria ícone na bandeja refletindo o modo atual (cor+letra) com menu marcando
    o modo ativo. `get_mode` retorna o modo atual (0/1/2). Retorna o objeto icon."""
    import pystray
    def _is(m): return lambda item: get_mode() == m
    menu = pystray.Menu(
        pystray.MenuItem(lambda item: f"Modo: {TRAY_MODE_NAMES.get(get_mode(), '?')}",
                         lambda i, it: on_show(), enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Abrir Haylou", lambda i, it: on_show(), default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("ANC", lambda i, it: on_anc(), checked=_is(1), radio=True),
        pystray.MenuItem("Transparência", lambda i, it: on_transp(), checked=_is(2), radio=True),
        pystray.MenuItem("Normal", lambda i, it: on_normal(), checked=_is(0), radio=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair", lambda i, it: on_quit()),
    )
    icon = pystray.Icon("haylou", _mode_icon_img(get_mode()),
                        f"Haylou S30 Pro — {TRAY_MODE_NAMES.get(get_mode(), '')}", menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return icon

def update_tray_mode(icon, mode: int):
    """Atualiza o ícone da bandeja pro modo atual (cor+letra+tooltip+menu)."""
    if not icon:
        return
    try:
        icon.icon = _mode_icon_img(mode)
        icon.title = f"Haylou S30 Pro — {TRAY_MODE_NAMES.get(mode, '')}"
        icon.update_menu()
    except Exception:
        pass

# ─── Auto-start no boot ───
def get_startup_path() -> str:
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup", "Haylou S30.lnk")

def set_autostart(enabled: bool, target_cmd: str = None) -> bool:
    """Cria/remove atalho na pasta Startup do Windows."""
    lnk = get_startup_path()
    if not enabled:
        try:
            if os.path.exists(lnk):
                os.remove(lnk)
            return True
        except Exception:
            return False
    # cria atalho via COM (pythoncom/win32com) ou PowerShell fallback
    try:
        py = sys.executable.replace("python.exe", "pythonw.exe")
        script = os.path.join(APP_DIR, "haylou_flet.py")
        ps = (f'powershell -NoProfile -Command "'
              f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut(\'{lnk}\');'
              f'$s.TargetPath=\'{py}\';$s.Arguments=\'\\\"{script}\\\"\';'
              f'$s.WorkingDirectory=\'{APP_DIR}\';$s.Save()"')
        os.system(ps)
        return os.path.exists(lnk)
    except Exception:
        return False

def is_autostart_enabled() -> bool:
    return os.path.exists(get_startup_path())
