"""
i18n — strings em PT-BR e EN. Detecta o idioma do Windows na 1ª vez; o usuário
pode trocar manualmente (salvo no config). Uso: i18n.t("chave") ou i18n.t("k", x=1).

Sem dependência externa: usa ctypes pra ler o idioma do SO. Fallback = EN
(o repo é público/internacional). Chave ausente cai no próprio nome da chave,
então nunca quebra a UI mesmo se faltar uma tradução.
"""
import ctypes

_lang = None  # "pt" | "en" — resolvido em set_lang()

STRINGS = {
    # genéricos / topo
    "app_name":        ("Haylou S30 Pro", "Haylou S30 Pro"),
    "starting":        ("iniciando", "starting"),
    "connecting":      ("conectando", "connecting"),
    "connected":       ("conectado", "connected"),
    "reconnecting":    ("reconectando…", "reconnecting…"),
    "not_found":       ("fone não encontrado", "headphones not found"),
    "proto_unknown":   ("conectado, mas protocolo não reconhecido (firmware?)",
                        "connected, but protocol not recognized (firmware?)"),
    # modos ANC
    "anc":             ("ANC", "ANC"),
    "transparency":    ("Transparência", "Transparency"),
    "normal":          ("Normal", "Normal"),
    "anc_desc":        ("Cancelamento de ruído", "Noise cancelling"),
    "transp_desc":     ("Som ambiente", "Ambient sound"),
    "normal_desc":     ("Sem processamento", "No processing"),
    # AUTO
    "auto":            ("AUTO", "AUTO"),
    "auto_on":         ("AUTO ligado — IA no comando", "AUTO on — AI in control"),
    "auto_off":        ("AUTO desligado — manual", "AUTO off — manual"),
    "auto_hint":       ("Troca o modo pelo contexto (música→ANC, call→Transparência, jogo→Game)",
                        "Switches mode by context (music→ANC, call→Transparency, game→Game)"),
    "mode_locked":     ("Modo travado — o AUTO não troca mais",
                        "Mode locked — AUTO won't change it"),
    "mode_unlocked":   ("Modo destravado", "Mode unlocked"),
    "lock_tip":        ("Travar o modo (impede o AUTO de trocar)",
                        "Lock the mode (stop AUTO from changing it)"),
    # game / leak
    "game_mode":       ("Game Mode", "Game Mode"),
    "low_latency":     ("baixa latência", "low latency"),
    "game_on":         ("Game Mode ON", "Game Mode ON"),
    "game_off":        ("Game Mode OFF", "Game Mode OFF"),
    "antileak":        ("Anti-vazamento", "Anti-leak"),
    "antileak_desc":   ("reduz som que escapa do fone", "reduces sound leaking out"),
    "antileak_on":     ("Anti-vazamento ON", "Anti-leak ON"),
    "antileak_off":    ("Anti-vazamento OFF", "Anti-leak OFF"),
    # áudio / EQ
    "audio":           ("Áudio", "Audio"),
    "pc_eq":           ("Equalizador do PC", "PC Equalizer"),
    "pc_eq_desc":      ("via Equalizer APO — vale toda saída do PC, não fica salvo no fone",
                        "via Equalizer APO — applies to all PC output, not saved on the device"),
    "eq_set":          ("EQ: {name}", "EQ: {name}"),
    "eq_unavailable":  ("EQ APO indisponível", "EQ APO unavailable"),
    "eq_reapplied":    ("EQ reaplicado: {name}", "EQ reapplied: {name}"),
    "spatial":         ("Som Espacial (Windows)", "Spatial Sound (Windows)"),
    # nomes de EQ (o valor real continua PT no winmedia; isto é só o display)
    "eq_Padrão":       ("Padrão", "Default"),
    "eq_Grave +":      ("Grave +", "Bass +"),
    "eq_Vocal":        ("Vocal", "Vocal"),
    "eq_Agudo +":      ("Agudo +", "Treble +"),
    "eq_Cinema":       ("Cinema", "Cinema"),
    "eq_Podcast":      ("Podcast", "Podcast"),
    "spatial_tip":     ("Abre o painel de Som Espacial do Windows (Sonic/Atmos)",
                        "Opens Windows Spatial Sound panel (Sonic/Atmos)"),
    # cenários (o ícone já aparece ao lado; aqui só o texto)
    "sc_focus":        ("Foco", "Focus"),
    "sc_game":         ("Jogo", "Gaming"),
    "sc_music":        ("Música", "Music"),
    "sc_call":         ("Call", "Call"),
    # now playing / mídia
    "nothing_playing": ("nada tocando", "nothing playing"),
    # bateria
    "batt_low":        ("Bateria baixa: {pct}%", "Low battery: {pct}%"),
    "batt_crit":       ("Bateria crítica: {pct}% — carregue o fone",
                        "Critical battery: {pct}% — charge your headphones"),
    # botões / tooltips
    "reconnect_tip":   ("Reconectar o fone", "Reconnect headphones"),
    "stats_tip":       ("Estatísticas de uso", "Usage statistics"),
    "theme_light":     ("Tema claro", "Light theme"),
    "theme_dark":      ("Tema escuro", "Dark theme"),
    "theme_light_set": ("Tema claro ☀️", "Light theme ☀️"),
    "theme_dark_set":  ("Tema escuro 🌙", "Dark theme 🌙"),
    "autostart_tip":   ("Abrir junto com o Windows", "Start with Windows"),
    "autostart_set":   ("Abre no boot: {on}", "Start on boot: {on}"),
    "lang_tip":        ("Idioma / Language", "Idioma / Language"),
    # estatísticas
    "stats_title":     ("Suas estatísticas (local)", "Your stats (local)"),
    "stats_empty":     ("Ainda sem dados. Use o app um tempo e o AUTO aprende seus hábitos.",
                        "No data yet. Use the app for a while and AUTO learns your habits."),
    "stats_total":     ("{n} trocas de modo registradas (local).",
                        "{n} mode switches recorded (local)."),
    "stats_top_apps":  ("Apps onde você mais troca:", "Apps where you switch the most:"),
    "close":           ("Fechar", "Close"),
    # onboarding / update
    "onboard":         ("Ligue seu Haylou e deixe perto do PC. Ctrl+Alt+A cicla o ANC de "
                        "qualquer lugar; o AUTO troca o modo conforme o que você faz.",
                        "Turn on your Haylou and keep it near the PC. Ctrl+Alt+A cycles ANC "
                        "from anywhere; AUTO switches the mode based on what you do."),
    "update_avail":    ("Nova versão disponível ({tag}) — clique pra baixar",
                        "New version available ({tag}) — click to download"),
    "open_download":   ("Abrir a página de download", "Open the download page"),
    # tray
    "tray_open":       ("Abrir Haylou", "Open Haylou"),
    "tray_quit":       ("Sair", "Quit"),
}


def _detect_windows_lang() -> str:
    """'pt' se o Windows estiver em português, senão 'en'."""
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        # 0x0416 pt-BR, 0x0816 pt-PT → primary language id 0x16 = Portuguese
        return "pt" if (lid & 0xFF) == 0x16 else "en"
    except Exception:
        return "en"


def set_lang(lang: str = None):
    """Define o idioma ('pt'/'en'). None = autodetecta pelo Windows."""
    global _lang
    if lang in ("pt", "en"):
        _lang = lang
    else:
        _lang = _detect_windows_lang()
    return _lang


def get_lang() -> str:
    if _lang is None:
        set_lang()
    return _lang


def t(key: str, **kwargs) -> str:
    """Traduz a chave pro idioma atual. Aceita format(**kwargs). Chave ausente
    retorna a própria chave (nunca quebra a UI)."""
    pair = STRINGS.get(key)
    if not pair:
        return key
    s = pair[0] if get_lang() == "pt" else pair[1]
    if kwargs:
        try:
            return s.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return s
    return s
