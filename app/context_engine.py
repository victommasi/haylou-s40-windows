"""
Motor de contexto: detecta o que o usuário está fazendo e sugere o modo ANC ideal.
100% local — usa janela em foco (Win32) + sessão de mídia (SMTC via winmedia).

Regras (do especialista):
  - Call/vídeo conferência em foco  -> Transparência (você precisa se ouvir)
  - Jogo em foco                    -> Game Mode ON + Normal/ANC
  - Música tocando                  -> ANC (imersão)
  - Vídeo tocando (não-música)      -> Normal
  - Nada relevante                  -> mantém
"""
import ctypes
from ctypes import wintypes
import winmedia as wm

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

# Apps de call/conferência -> Transparência
CALL_APPS = ("zoom", "teams", "meet", "discord", "skype", "webex", "slack",
             "whatsapp", "telegram", "googlemeet", "ms-teams")
# Jogos / launchers -> Game Mode
GAME_APPS = ("steam", "epicgames", "leagueclient", "valorant", "csgo", "cs2",
             "dota2", "riotclient", "battle.net", "game", "minecraft")
# Browsers (contexto depende do que toca)
BROWSERS = ("chrome", "msedge", "firefox", "brave", "opera")

# modos: 0=Normal, 1=ANC, 2=Transparência
MODE_NORMAL, MODE_ANC, MODE_TRANSP = 0, 1, 2


def get_foreground_process() -> str:
    """Nome do .exe da janela em foco (lowercase, sem extensão). '' se falhar."""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        PROCESS_QUERY_LIMITED = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = wintypes.DWORD(512)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                exe = buf.value.split("\\")[-1].lower()
                return exe.replace(".exe", "")
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        pass
    return ""


def get_foreground_title() -> str:
    """Título da janela em foco (lowercase)."""
    try:
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.lower()
    except Exception:
        return ""


def suggest_mode():
    """Retorna (modo_anc, game_mode_bool, motivo). modo_anc None = não mexe."""
    proc = get_foreground_process()
    title = get_foreground_title()

    # 1) Jogo em foco -> Game Mode
    if any(g in proc for g in GAME_APPS):
        return (MODE_NORMAL, True, f"jogo ({proc})")

    # 2) Call/conferência em foco -> Transparência
    if any(c in proc for c in CALL_APPS):
        return (MODE_TRANSP, False, f"call ({proc})")
    # browser numa call (meet/teams web): título denuncia
    if any(b in proc for b in BROWSERS):
        if any(k in title for k in ("meet", "zoom", "teams", "webex", "call", "reunião", "reuniao")):
            return (MODE_TRANSP, False, "call no browser")

    # 3) Música tocando -> ANC (imersão). Vídeo/outro áudio -> Normal.
    try:
        sessions = wm.get_now_playing()
        playing = next((s for s in sessions if s["playing"]), None)
        if playing:
            app = playing["app"].lower()
            # música dedicada = ANC (você quer imersão)
            if any(m in app for m in ("spotify", "music", "groove", "tidal", "deezer",
                                       "youtube music", "amazonmusic", "foobar", "aimp")):
                return (MODE_ANC, False, f"música ({playing['app']})")
            # vídeo/podcast/browser tocando = Normal (ANC pesado não ajuda, e te isola)
            return (MODE_NORMAL, False, f"vídeo/áudio ({playing['app']})")
    except Exception:
        pass

    # 4) trabalho concentrado (editor/terminal/doc) sem áudio -> ANC pra focar.
    #    Só quando NADA toca: se tocar algo, a regra 3 acima já decidiu.
    FOCUS_APPS = ("code", "devenv", "pycharm", "idea", "sublime", "cursor",
                  "windowsterminal", "powershell", "cmd", "wt",
                  "winword", "excel", "powerpnt", "notion", "obsidian")
    if any(f in proc for f in FOCUS_APPS):
        return (MODE_ANC, False, f"foco ({proc})")

    # 5) nada relevante -> não mexe
    return (None, None, "sem contexto claro")
