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
        # utf-8-sig tolera BOM (ex: se o config for escrito por fora com PowerShell)
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
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

# ─── Instância única (impede abrir 2 cópias que brigam pela conexão BLE) ───
_mutex_handle = None
def acquire_single_instance(name: str = "HaylouS30ProWindowsApp_SingleInstance") -> bool:
    """True se esta é a 1ª instância; False se já existe outra rodando.
    Mutex nomeado do Windows (vive enquanto o processo viver). Em caso de falha
    na checagem, retorna True pra não travar o app injustamente."""
    global _mutex_handle
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        k.CreateMutexW.restype = wintypes.HANDLE
        k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        _mutex_handle = k.CreateMutexW(None, True, name)
        ERROR_ALREADY_EXISTS = 183
        return k.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return True

def focus_existing_window(title: str = "Haylou S30 Pro") -> bool:
    """Traz a janela da instância já aberta pra frente (em vez de abrir outra)."""
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, title)
        if hwnd:
            u.ShowWindow(hwnd, 9)        # SW_RESTORE (desminimiza)
            u.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False

def release_single_instance():
    """Libera o mutex de instância única (pra um re-exec não bater na própria trava)."""
    global _mutex_handle
    try:
        if _mutex_handle:
            import ctypes
            ctypes.windll.kernel32.ReleaseMutex(_mutex_handle)
            ctypes.windll.kernel32.CloseHandle(_mutex_handle)
            _mutex_handle = None
    except Exception:
        pass

def relaunch_self():
    """Reinicia o app limpo (re-exec). Usado pra trocar idioma sem deixar worker/
    hotkeys/threads duplicados. Libera o mutex, sobe uma nova instância com um pequeno
    atraso (pra esta sair antes) e encerra a atual."""
    import subprocess
    if getattr(sys, "frozen", False):
        target = [sys.executable]                      # rodando como .exe
    else:
        target = [sys.executable, os.path.abspath(sys.argv[0])]  # dev: python script
    release_single_instance()
    # cmd que espera ~1.2s e então sobe o app de novo (dá tempo da atual encerrar)
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        quoted = " ".join(f'"{a}"' for a in target)
        subprocess.Popen(f'timeout /t 2 /nobreak >nul & {quoted}',
                         shell=True, creationflags=flags, close_fds=True)
    os._exit(0)

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

def _tray_t(key, fallback):
    """Tradução pro tray sem acoplar forte: usa i18n se disponível, senão o fallback PT."""
    try:
        import i18n
        return i18n.t(key)
    except Exception:
        return fallback

def _tray_title(get_mode, get_batt):
    """Tooltip do tray: modo + bateria (se conhecida)."""
    mode = TRAY_MODE_NAMES.get(get_mode(), "")
    batt = get_batt() if get_batt else None
    suffix = f" · {batt}%" if isinstance(batt, int) else ""
    return f"Haylou S30 Pro — {mode}{suffix}"

def make_tray(on_show, on_anc, on_transp, on_normal, on_quit, get_mode=lambda: 1,
              get_batt=None, on_cycle=None):
    """Cria ícone na bandeja refletindo o modo atual (cor+letra) com menu marcando
    o modo ativo. `get_mode` retorna o modo (0/1/2). `get_batt` retorna bateria %
    (ou None) pro tooltip. `on_cycle` (opcional) é chamado no clique ESQUERDO do
    ícone pra ciclar o ANC sem abrir a janela. Retorna o objeto icon."""
    import pystray
    def _is(m): return lambda item: get_mode() == m
    # clique esquerdo no ícone cicla o ANC (se on_cycle dado); senão abre a janela.
    default_action = (lambda i, it: on_cycle()) if on_cycle else (lambda i, it: on_show())
    menu = pystray.Menu(
        pystray.MenuItem(lambda item: _tray_title(get_mode, get_batt),
                         lambda i, it: on_show(), enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Trocar ANC (clique no ícone)", default_action, default=True, visible=False),
        pystray.MenuItem(_tray_t("tray_open", "Abrir Haylou"), lambda i, it: on_show()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("ANC", lambda i, it: on_anc(), checked=_is(1), radio=True),
        pystray.MenuItem("Transparência", lambda i, it: on_transp(), checked=_is(2), radio=True),
        pystray.MenuItem("Normal", lambda i, it: on_normal(), checked=_is(0), radio=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(_tray_t("tray_quit", "Sair"), lambda i, it: on_quit()),
    )
    icon = pystray.Icon("haylou", _mode_icon_img(get_mode()),
                        _tray_title(get_mode, get_batt), menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return icon

def update_tray_mode(icon, mode: int, get_mode=None, get_batt=None):
    """Atualiza o ícone da bandeja pro modo atual (cor+letra+tooltip+menu).
    Passa get_mode/get_batt pra recompor o tooltip com bateria; sem eles, só o modo."""
    if not icon:
        return
    try:
        icon.icon = _mode_icon_img(mode)
        if get_mode:
            icon.title = _tray_title(get_mode, get_batt)
        else:
            icon.title = f"Haylou S30 Pro — {TRAY_MODE_NAMES.get(mode, '')}"
        icon.update_menu()
    except Exception:
        pass

# ─── Ícone da janela (titlebar + taskbar) ───
def set_app_user_model_id(app_id: str = "RevoluteDigital.HaylouS30Pro"):
    """Define o AppUserModelID do processo. Sem isso o Windows agrupa o app pelo
    processo do Flet e mostra o ícone genérico do Flet na BARRA DE TAREFAS (mesmo
    com o ícone da janela já trocado). Com um ID próprio, a taskbar usa o ícone
    da janela (s30.ico). Tem que ser chamado ANTES da janela aparecer."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def set_window_icon(title: str, ico_path: str, retries: int = 40):
    """Força o ícone da janela via WM_SETICON. O Flet desktop senão mostra o logo
    do Flet (o --icon do PyInstaller só troca o ícone do arquivo .exe). Espera a
    janela aparecer, em thread (não bloqueia). Tipos cuidados pra handle 64-bit."""
    import time as _t
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    u.FindWindowW.restype = wintypes.HWND
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.LoadImageW.restype = ctypes.c_void_p
    u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                             ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p]
    WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
    IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x0010, 0x0040

    def _do():
        if not os.path.exists(ico_path):
            return
        for _ in range(retries):
            hwnd = u.FindWindowW(None, title)
            if hwnd:
                big = u.LoadImageW(None, ico_path, IMAGE_ICON, 0, 0,
                                   LR_LOADFROMFILE | LR_DEFAULTSIZE)
                small = u.LoadImageW(None, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                if big:
                    u.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big)
                    u.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small or big)
                    return
            _t.sleep(0.4)
    threading.Thread(target=_do, daemon=True).start()

# ─── Auto-start no boot ───
def get_startup_path() -> str:
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup", "Haylou S30.lnk")

def _autostart_target():
    """Decide pra onde o atalho de boot aponta. Prioriza o .exe (app de verdade,
    sem depender de Python):
      1. rodando como .exe empacotado  → o próprio executável
      2. rodando como script + .exe já buildado em dist/ → aponta pro .exe
      3. fallback dev → pythonw + haylou_flet.py
    Retorna (target_path, arguments, working_dir)."""
    if getattr(sys, "frozen", False):
        return sys.executable, "", os.path.dirname(sys.executable)
    built_exe = os.path.join(APP_DIR, "dist", "Haylou S30 Pro.exe")
    if os.path.exists(built_exe):
        return built_exe, "", os.path.dirname(built_exe)
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    return pyw, f'"{os.path.join(APP_DIR, "haylou_flet.py")}"', APP_DIR

def set_autostart(enabled: bool, target_cmd: str = None) -> bool:
    """Cria/remove atalho na pasta Startup do Windows (aponta pro .exe quando existe)."""
    lnk = get_startup_path()
    if not enabled:
        try:
            if os.path.exists(lnk):
                os.remove(lnk)
            return True
        except Exception:
            return False
    try:
        target, args, workdir = _autostart_target()
        ps = (f'powershell -NoProfile -Command "'
              f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut(\'{lnk}\');'
              f'$s.TargetPath=\'{target}\';$s.Arguments=\'{args}\';'
              f'$s.WorkingDirectory=\'{workdir}\';$s.Save()"')
        os.system(ps)
        return os.path.exists(lnk)
    except Exception:
        return False

def is_autostart_enabled() -> bool:
    return os.path.exists(get_startup_path())
