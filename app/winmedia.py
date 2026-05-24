"""
Helpers de mídia/volume do Windows pra central de mídia.
Volume: pycaw (API de áudio do Windows).
Mídia (play/pause/next/prev): teclas de mídia virtuais (funciona com qualquer player).
"""
import ctypes
import warnings
from ctypes import cast, POINTER
import comtypes

# silencia RuntimeWarning cosmetico de coroutine (winrt async em loop isolado)
warnings.filterwarnings("ignore", category=RuntimeWarning, module="winmedia")
warnings.filterwarnings("ignore", message=".*coroutine.*never awaited.*")
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities
from pycaw.api.endpointvolume import IAudioEndpointVolume

_com_ready = False
def _ensure_com():
    global _com_ready
    if not _com_ready:
        try: comtypes.CoInitialize()
        except Exception: pass
        _com_ready = True

# Virtual key codes de mídia
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_VOLUME_MUTE = 0xAD
KEYEVENTF_KEYUP = 0x0002

def _tap(vk):
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

def play_pause(): _tap(VK_MEDIA_PLAY_PAUSE)
def next_track(): _tap(VK_MEDIA_NEXT_TRACK)
def prev_track(): _tap(VK_MEDIA_PREV_TRACK)
def toggle_mute(): _tap(VK_VOLUME_MUTE)

# ─── Volume (pycaw) ───
# Cacheia a interface de volume (evita recriar COM toda hora = causa do access violation
# no shutdown). Uma instancia, reusada.
_vol_cache = None
def _vol_iface():
    global _vol_cache
    if _vol_cache is not None:
        return _vol_cache
    _ensure_com()
    spk = AudioUtilities.GetSpeakers()
    dev = spk._dev if hasattr(spk, "_dev") else spk
    interface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    _vol_cache = cast(interface, POINTER(IAudioEndpointVolume))
    return _vol_cache

def get_volume():
    """0-100"""
    try:
        return int(round(_vol_iface().GetMasterVolumeLevelScalar() * 100))
    except Exception:
        return None

def set_volume(pct):
    """pct 0-100"""
    try:
        _vol_iface().SetMasterVolumeLevelScalar(max(0.0, min(1.0, pct/100.0)), None)
        return True
    except Exception:
        return False

def is_muted():
    try:
        return bool(_vol_iface().GetMute())
    except Exception:
        return False

# ─── Sessão de mídia (SMTC: o que está tocando + qual player) ───
import asyncio as _asyncio

def _app_friendly(app_id: str) -> str:
    """Converte AppUserModelId num nome amigável."""
    if not app_id:
        return "?"
    m = {
        "spotify": "Spotify", "msedge": "Edge", "chrome": "Chrome",
        "firefox": "Firefox", "vlc": "VLC", "zune": "Groove",
        "music.ui": "Apple Music", "wmplayer": "Windows Media",
        "brave": "Brave", "opera": "Opera", "youtube": "YouTube",
    }
    low = app_id.lower()
    for k, v in m.items():
        if k in low:
            return v
    # pega o ultimo segmento legivel
    seg = app_id.replace("!", ".").split(".")
    return seg[0][:18] if seg else app_id[:18]

async def _get_sessions_async():
    from winrt.windows.media.control import \
        GlobalSystemMediaTransportControlsSessionManager as Mgr
    mgr = await Mgr.request_async()
    cur = mgr.get_current_session()
    sessions = list(mgr.get_sessions())
    out = []
    for s in sessions:
        try:
            info = await s.try_get_media_properties_async()
            pb = s.get_playback_info()
            playing = bool(pb and pb.playback_status == 4)  # 4 = PLAYING
            out.append({
                "app": _app_friendly(s.source_app_user_model_id),
                "app_id": s.source_app_user_model_id,
                "title": info.title or "",
                "artist": info.artist or "",
                "playing": playing,
                "is_current": (cur is not None and
                               s.source_app_user_model_id == cur.source_app_user_model_id),
            })
        except Exception:
            pass
    return out

# ─── EQ APO (equalização via software — supre o EQ que o S30 não tem) ───
import os as _os

EQ_APO_CONFIG = r"C:\Program Files\EqualizerAPO\config\config.txt"

# perfis de EQ corretivos (ganhos por banda Hz). Suave/seguro (só pequenos boosts/cuts).
EQ_PROFILES = {
    "Padrão":     [],
    "Grave +":    [(60, 5), (150, 3), (400, 0), (1000, 0), (3000, 0), (8000, 0)],
    "Vocal":      [(60, -2), (300, 0), (1000, 2), (3000, 4), (6000, 2), (10000, 0)],
    "Agudo +":    [(60, 0), (1000, 0), (3000, 2), (6000, 4), (12000, 5)],
    "Cinema":     [(40, 4), (200, 1), (1000, -1), (3000, 1), (8000, 3)],
    "Podcast":    [(60, -4), (200, -1), (1500, 3), (4000, 3), (8000, 1)],
}

def set_eq_apo(profile_name: str) -> bool:
    """Escreve um perfil de EQ no Equalizer APO (aplica em qualquer saída de áudio)."""
    if not _os.path.exists(EQ_APO_CONFIG):
        return False
    bands = EQ_PROFILES.get(profile_name, [])
    lines = ["# Haylou Central — perfil: " + profile_name]
    if bands:
        for hz, gain in bands:
            lines.append(f"Filter: ON PK Fc {hz} Hz Gain {gain} dB Q 1.0")
    else:
        lines.append("# (sem equalização — plano)")
    try:
        with open(EQ_APO_CONFIG, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception:
        return False

def eq_apo_available() -> bool:
    return _os.path.exists(EQ_APO_CONFIG)

# ─── Auto-reaplicar: o APO reseta o config.txt quando troca de dispositivo de
#     áudio ou atualiza. Marcamos o arquivo com um header; se o header sumir,
#     foi resetado por fora → reescreve o perfil escolhido. ───
import time as _time
import threading as _threading

def _eq_header(profile_name: str) -> str:
    return "# Haylou Central — perfil: " + profile_name

def eq_apo_intact(profile_name: str) -> bool:
    """True se o config do APO ainda é o nosso (header presente)."""
    try:
        with open(EQ_APO_CONFIG, encoding="utf-8") as f:
            return _eq_header(profile_name) in f.read()
    except Exception:
        return False

def watch_eq_apo(get_profile_name, interval: float = 4.0, on_reapply=None):
    """Thread daemon: se o config do APO for resetado por fora, reaplica o perfil
    atual. `get_profile_name` retorna o nome do perfil ativo; `on_reapply(name)`
    (opcional) é chamado quando reaplica."""
    def _loop():
        while True:
            _time.sleep(interval)
            try:
                name = get_profile_name()
                if name in EQ_PROFILES and not eq_apo_intact(name):
                    if set_eq_apo(name) and on_reapply:
                        on_reapply(name)
            except Exception:
                pass
    t = _threading.Thread(target=_loop, daemon=True)
    t.start()
    return t

# ─── Windows Spatial Sound (Windows Sonic — supre o spatial que o S30 não tem) ───
def toggle_spatial_panel():
    """Abre o painel de som espacial do Windows (toggle manual mais confiável que via reg)."""
    try:
        _os.system("start ms-settings:sound")
        return True
    except Exception:
        return False

def get_now_playing():
    """Lista de players ativos com {app,title,artist,playing,is_current}. [] se nenhum.
    Event loop próprio + COM inicializado (chamado de thread sem loop/COM)."""
    try:
        comtypes.CoInitialize()
    except Exception:
        pass
    loop = _asyncio.new_event_loop()
    _asyncio.set_event_loop(loop)
    coro = None
    try:
        coro = _get_sessions_async()
        return loop.run_until_complete(coro)
    except Exception:
        # garante que a coroutine seja fechada (evita 'never awaited')
        if coro is not None:
            try: coro.close()
            except Exception: pass
        return []
    finally:
        try: loop.close()
        except Exception: pass
        _asyncio.set_event_loop(None)
