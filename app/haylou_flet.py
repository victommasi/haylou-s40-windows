#!/usr/bin/env python3
"""
Haylou S30 Pro — Central de Mídia (Windows).
Controle ANC + Game Mode + mídia + volume, com visual premium (Flet).
Conexão BLE persistente, funciona com áudio conectado.
Protocolo reverso-engenheirado do app Haylou Sound v1.5.3 (ver docs/).
"""
import asyncio
import threading
import queue
import time
import os
import sys
import flet as ft
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
import winmedia as wm
import haylou_protocol as proto
import context_engine as ce
import system_integration as sysint
import usage_map as um
import battery_log as blog
import updater
import i18n
from i18n import t

CF_WRITE  = "0000cf05-0000-1000-8000-00805f9b34fb"
CF_NOTIFY = "0000cf06-0000-1000-8000-00805f9b34fb"
ADDR_HINTS = ("BB:AD:EE",)  # OUI da Haylou — usado pra achar o fone no scan
# vazio = procura qualquer fone Haylou no scan. O endereço real do SEU fone é
# descoberto e salvo no config.json na 1ª conexão (não vem chumbado no código).
KNOWN_ADDR = ""

def _asset(name: str) -> str:
    """Caminho de um asset, funcionando em dev E dentro do .exe (PyInstaller _MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)

# ═══════════════════ DESIGN TOKENS ═══════════════════
class T:
    # ── constantes (NÃO mudam com o tema) ──
    ANC      = "#FF3B5C"
    TRANSP   = "#3B82F6"
    NORMAL   = "#64748B"
    R_CARD   = 18
    R_PILL   = 999
    F = "Segoe UI"
    # ── dependentes de tema (preenchidos por apply_palette) ──
    BG = SURFACE = SURFACE2 = BORDER = TXT = TXT_DIM = TXT_FAINT = OK = WARN = ""

# Paletas: dark = original premium quase-preto. light = fundo branco/claro.
# Accent (ANC/TRANSP/NORMAL) é constante; só superfícies/texto/semântico mudam.
PALETTES = {
    "dark":  dict(BG="#08080F", SURFACE="#13131F", SURFACE2="#1B1B2A", BORDER="#26263A",
                  TXT="#FFFFFF", TXT_DIM="#8B8B9E", TXT_FAINT="#5A5A6E",
                  OK="#22D67B", WARN="#FBBF24"),
    "light": dict(BG="#F4F5F7", SURFACE="#FFFFFF", SURFACE2="#EDF0F4", BORDER="#DCE1E8",
                  TXT="#0E1116", TXT_DIM="#586072", TXT_FAINT="#98A1B0",
                  OK="#16A34A", WARN="#D97706"),
}
THEMED_KEYS = ("BG", "SURFACE", "SURFACE2", "BORDER", "TXT", "TXT_DIM", "TXT_FAINT", "OK", "WARN")

def apply_palette(name: str):
    for k, v in PALETTES.get(name, PALETTES["dark"]).items():
        setattr(T, k, v)

apply_palette("dark")  # default no import; main() reaplica conforme o config

# chave i18n por modo (nome e descrição traduzidos na hora do acesso)
_MODE_KEY  = {0: "normal", 1: "anc", 2: "transparency"}
_MODE_DESC = {0: "normal_desc", 1: "anc_desc", 2: "transp_desc"}

class _ModeNames:
    """dict-like: MODE_NAMES[m] devolve o nome do modo traduzido no idioma atual."""
    def __getitem__(self, m): return t(_MODE_KEY.get(m, "anc"))
    def get(self, m, default=""): return t(_MODE_KEY[m]) if m in _MODE_KEY else default
MODE_NAMES = _ModeNames()

def anc_modes():
    """Lista (nome, modo, cor, ícone, descrição) com textos traduzidos."""
    return [
        (t("anc"),          1, T.ANC,    ft.Icons.NOISE_CONTROL_OFF, t("anc_desc")),
        (t("transparency"), 2, T.TRANSP, ft.Icons.HEARING,           t("transp_desc")),
        (t("normal"),       0, T.NORMAL, ft.Icons.MUSIC_NOTE,        t("normal_desc")),
    ]
MODE_COLOR = {1:T.ANC, 2:T.TRANSP, 0:T.NORMAL}
MODE_ICON  = {1:ft.Icons.NOISE_CONTROL_OFF, 2:ft.Icons.HEARING, 0:ft.Icons.MUSIC_NOTE}

GET_BATTERY = proto.build_get_battery()
GET_ANC = proto.build_get_anc()

# ═══════════════════ BLE WORKER (lógica testada — inalterada) ═══════════════════
class BleWorker:
    def __init__(self, on_status, on_batt, on_mode=None, on_game=None, on_leak=None,
                 addr=None, on_device=None):
        self.q = queue.Queue()
        self.on_status = on_status; self.on_batt = on_batt
        self.on_mode = on_mode; self.on_game = on_game; self.on_leak = on_leak
        self.addr = addr or KNOWN_ADDR   # multi-fone: endereço alvo (config ou default)
        self.on_device = on_device       # callback(addr, name) ao achar/lembrar o fone
        self.client = None
        self._valid_seen = False         # já recebeu algum frame que o protocolo reconhece?
        threading.Thread(target=lambda: asyncio.run(self._loop()), daemon=True).start()

    def send(self, kind, value=None): self.q.put((kind, value))

    def _has_control_service(self) -> bool:
        """True se a tabela GATT atual expõe o serviço de controle (cf00/cf06).
        Às vezes o fone conecta mas só publica os serviços genéricos (1800/180a) —
        estado 'capado' que acontece quando ele fica ocioso ou disputa o canal com
        outro host. Nesse estado o controle ANC não funciona, então tratamos como
        NÃO-conectado e reconectamos, em vez de ficar mudo."""
        try:
            for svc in self.client.services:
                if svc.uuid.lower().startswith("0000cf06") or svc.uuid.lower().startswith("0000cf00"):
                    return True
                for ch in svc.characteristics:
                    if ch.uuid.lower() == CF_NOTIFY:
                        return True
        except Exception:
            return False
        return False

    async def _try_client(self, ble_device, timeout: float, force_fresh: bool = False) -> bool:
        """Conecta num BLEDevice e SÓ considera sucesso se o serviço de controle
        aparecer. force_fresh ignora o cache de serviços do Windows (que pode ter
        guardado uma tabela capada antiga)."""
        winrt = {"use_cached_services": False} if force_fresh else {}
        self.client = BleakClient(ble_device, timeout=timeout, winrt=winrt)
        await self.client.connect()
        if not self.client.is_connected:
            return False
        if not self._has_control_service():
            # conectou mas veio capado — desconecta pra forçar nova descoberta depois
            try: await self.client.disconnect()
            except Exception: pass
            self.client = None
            return False
        await self.client.start_notify(CF_NOTIFY, self._notify)
        return True

    async def _connect(self):
        if self.client and self.client.is_connected and self._has_control_service():
            return True
        self.on_status(t("connecting"), T.WARN)
        # 1) endereço conhecido. Passa BLEDevice (não string): no Windows o fone não
        #    anuncia BLE já-conectado-como-áudio; bleak 3.x com string faz um scan que
        #    falha. Com BLEDevice conecta direto via from_bluetooth_address.
        #    Tenta com cache; se vier capado (sem cf00/cf06), retenta forçando
        #    re-descoberta sem cache (o cache do Windows às vezes guarda tabela velha).
        if self.addr:
            for force_fresh in (False, True):
                try:
                    if await self._try_client(BLEDevice(self.addr, "HAYLOU S30", None),
                                              timeout=8.0, force_fresh=force_fresh):
                        self.on_status(t("connected"), T.OK); return True
                except Exception: pass
        # fallback: escaneia e conecta no 1º fone Haylou (e lembra o endereço).
        try:
            for d in await BleakScanner.discover(timeout=4.0):
                if d.address.upper().startswith(ADDR_HINTS):
                    try:
                        if await self._try_client(d, timeout=6.0):
                            self.addr = d.address
                            if self.on_device:
                                try: self.on_device(d.address, getattr(d, "name", None))
                                except Exception: pass
                            self.on_status(t("connected"), T.OK); return True
                    except Exception: pass
        except Exception: pass
        # chegou aqui = ou offline, ou no estado capado. Mensagem acionável: cobre
        # tanto a 1ª conexão (fone desligado/longe) quanto o estado travado.
        self.on_status(t("not_found"), T.ANC); return False

    def _notify(self, _, data):
        b = bytes(data)
        pct = proto.parse_battery(b)
        if pct is not None: self.on_batt(pct); self._valid_seen = True
        if self.on_mode:
            m = proto.parse_anc_mode(b)
            if m is not None: self.on_mode(m); self._valid_seen = True
        if self.on_game:
            g = proto.parse_game_mode(b)
            if g is not None: self.on_game(g); self._valid_seen = True
        if self.on_leak:
            lk = proto.parse_attr(b, proto.ORD_LEAK)
            if lk in (0, 1): self.on_leak(bool(lk)); self._valid_seen = True

    async def _compat_check(self):
        """Resiliência de firmware: se conectou mas em ~8s nada do protocolo foi
        reconhecido, avisa (firmware do fone provavelmente mudou) em vez de ficar
        mudo. Não bloqueia nada — só informa."""
        await asyncio.sleep(8)
        if self.client and self.client.is_connected and not self._valid_seen:
            self.on_status(t("proto_unknown"), T.WARN)

    async def _poll_battery(self):
        """Watchdog: pede status periodicamente E reconecta sozinho se a conexão
        caiu ou ficou capada (cf00/cf06 sumiram). Assim o usuário não precisa mais
        desligar/ligar o fone na mão — o app se recupera quando o fone volta."""
        while True:
            await asyncio.sleep(30)
            self.q.put(("reconnect", None))
            self.q.put(("status", None))

    async def _loop(self):
        await self._connect(); await self._status()
        asyncio.create_task(self._poll_battery())
        asyncio.create_task(self._compat_check())
        while True:
            kind, value = await asyncio.get_event_loop().run_in_executor(None, self.q.get)
            if kind == "quit": break
            if kind == "reconnect":
                # só re-tenta se realmente caiu/capou (não reconecta à toa)
                if not (self.client and self.client.is_connected and self._has_control_service()):
                    await self._connect()
                continue
            if kind == "force_reconnect":
                # botão "reconectar agora": derruba a conexão atual e refaz do zero
                self.on_status(t("reconnecting"), T.WARN)
                try:
                    if self.client: await self.client.disconnect()
                except Exception: pass
                self.client = None
                if await self._connect(): await self._status()
                continue
            if not await self._connect(): continue
            try:
                if kind == "anc":
                    await self.client.write_gatt_char(CF_WRITE, proto.build_set_anc(value), response=False)
                    self.on_status(f"{MODE_NAMES[value]}", T.OK)
                elif kind == "game":
                    await self.client.write_gatt_char(CF_WRITE, proto.build_set_game(bool(value)), response=False)
                    self.on_status(f"Game Mode {'ON' if value else 'OFF'}", T.OK)
                elif kind == "leak":
                    await self.client.write_gatt_char(CF_WRITE, proto.build_set_antileak(bool(value)), response=False)
                    self.on_status(f"Anti-vazamento {'ON' if value else 'OFF'}", T.OK)
                elif kind == "status":
                    await self._status()
            except Exception as e:
                self.on_status(f"erro {type(e).__name__}", T.ANC)
                try: await self.client.disconnect()
                except Exception: pass
                self.client = None

    async def _status(self):
        try:
            await self.client.write_gatt_char(CF_WRITE, GET_BATTERY, response=False)
            await self.client.write_gatt_char(CF_WRITE, proto.build_get_all(), response=False)
        except Exception: pass


# ═══════════════════ UI PREMIUM ═══════════════════
def main(page: ft.Page):
    import os
    # define um AppUserModelID proprio ANTES da janela aparecer, pra a barra de
    # tarefas usar o icone do app (s30.ico) em vez do icone generico do Flet.
    sysint.set_app_user_model_id()
    # idioma: usa o salvo no config, senão autodetecta pelo Windows (pt/en)
    i18n.set_lang(sysint.load_config().get("lang"))
    page.title = "Haylou S30 Pro"
    page.window.width = 400
    page.window.height = 860  # compacto: tudo cabe sem rolar
    page.window.resizable = False
    page.window.title_bar_hidden = False
    page.window.prevent_close = True  # fechar (X) esconde pro tray em vez de encerrar
    _theme = sysint.load_config().get("theme", "dark")  # tema salvo (dark|light)
    apply_palette(_theme)
    page.bgcolor = T.BG
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO  # rola quando o conteúdo passa da altura da janela
    page.theme_mode = ft.ThemeMode.LIGHT if _theme == "light" else ft.ThemeMode.DARK
    page.fonts = {}
    # ícone da janela/taskbar. s30.ico foi sobrescrito com o logo novo e vai embutido
    # no .exe. page.window.icon não basta no Flet desktop → forçamos via WM_SETICON.
    _ico = _asset("s30.ico")
    try:
        page.window.icon = _ico
    except Exception:
        pass
    sysint.set_window_icon("Haylou S30 Pro", _ico)

    state = {"mode": 1, "batt": None, "game": False, "auto": False, "last_auto": None,
             "ctx_app": ""}  # ctx_app = último app REAL em foco (ignora a janela do Haylou)
    tray = {"icon": None}  # ícone da bandeja (atualiza com o modo)

    # lock de interação: quando o user mexe num controle, ignora updates do device
    # por LOCK_MS (evita notify atrasado reverter o que o user acabou de fazer)
    LOCK_MS = 5.0
    touched = {}
    def mark_touch(name): touched[name] = time.time()
    def is_locked(name): return (time.time() - touched.get(name, 0)) < LOCK_MS

    state["mode_locked"] = False  # cadeado: trava o modo (AUTO não mexe)

    # ─── HERO: card grande do modo ativo (com glow + cadeado de override) ───
    # hero sempre tem fundo de cor de modo (accent) → texto branco em ambos os temas.
    # uso "#FEFEFE" (branco-sentinela) pra varredura de tema NÃO trocar pra preto no light.
    hero_icon = ft.Icon(MODE_ICON[1], color="#FEFEFE", size=34)
    hero_name = ft.Text(t("anc"), size=22, weight=ft.FontWeight.W_800, color="#FEFEFE")
    hero_desc = ft.Text(t("anc_desc"), size=12, color="#FEFEFE", opacity=0.7)
    hero_lock = ft.Container(
        content=ft.Icon(ft.Icons.LOCK_OPEN, color="#FEFEFE", size=20),
        ink=True, on_click=lambda e: toggle_lock(), padding=6, border_radius=99,
        tooltip=t("lock_tip"),
        opacity=0.6,
    )
    hero = ft.Container(
        content=ft.Row([
            hero_icon,
            ft.Column([hero_name, hero_desc], spacing=1, tight=True, expand=True),
            hero_lock,
        ], spacing=14, alignment=ft.MainAxisAlignment.START,
           vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(vertical=15, horizontal=22),
        border_radius=T.R_CARD,
        bgcolor=T.ANC,
        shadow=ft.BoxShadow(blur_radius=32, spread_radius=-6, color=T.ANC, offset=ft.Offset(0, 8)),
        animate=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
    )

    def set_lock(on):
        """Liga/desliga o cadeado do modo. Travado = a IA (AUTO) não troca o modo."""
        state["mode_locked"] = on
        hero_lock.content.name = ft.Icons.LOCK if on else ft.Icons.LOCK_OPEN
        hero_lock.content.color = T.WARN if on else "#FEFEFE"
        hero_lock.opacity = 1.0 if on else 0.6
        try: page.update()
        except Exception: pass

    def toggle_lock():
        set_lock(not state["mode_locked"])
        set_status(t("mode_locked") if state["mode_locked"] else t("mode_unlocked"),
                   T.WARN if state["mode_locked"] else T.TXT_DIM)

    def paint_hero(modo):
        c = MODE_COLOR[modo]
        hero.bgcolor = c
        hero.shadow = ft.BoxShadow(blur_radius=34, spread_radius=-6, color=c, offset=ft.Offset(0, 8))
        hero_icon.name = MODE_ICON[modo]
        hero_name.value = MODE_NAMES[modo]
        hero_desc.value = next((d for n,m,col,i,d in anc_modes() if m==modo), "")
        sysint.update_tray_mode(tray["icon"], modo,  # reflete modo+bateria no tray
                                get_mode=lambda: state["mode"], get_batt=lambda: state["batt"])
        page.update()

    # ─── chips de modo (compactos, abaixo do hero) ───
    chips = {}
    def make_chip(name, modo, color, icon, desc):
        chip = ft.Container(
            content=ft.Column([
                ft.Icon(icon, color=T.TXT, size=20),
                ft.Text(name, size=11, weight=ft.FontWeight.W_600, color=T.TXT,
                        text_align=ft.TextAlign.CENTER),
            ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
            width=104, height=62, border_radius=14,
            bgcolor=T.SURFACE, border=ft.Border.all(2, T.SURFACE),
            alignment=ft.Alignment(0, 0), ink=True,
            on_click=lambda e, m=modo: on_anc(m),
            animate=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
            animate_scale=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
        )
        chips[modo] = (chip, color)
        return chip

    def paint_chips(modo):
        for m, (chip, color) in chips.items():
            on = (m == modo)
            chip.border = ft.Border.all(2, color if on else T.SURFACE)
            chip.bgcolor = ft.Colors.with_opacity(0.16, color) if on else T.SURFACE  # tint do accent
        page.update()

    def _persist(key, value):
        """Salva o último estado de um controle no config, pra restaurar ao reabrir
        (o fone, se desconectado no boot, não reporta — então mostramos o que o
        usuário deixou na última vez)."""
        try:
            c = sysint.load_config(); c[key] = value; sysint.save_config(c)
        except Exception: pass

    def on_anc(modo):
        state["mode"] = modo
        mark_touch("anc")
        _persist("last_anc", modo)
        # se a IA (AUTO) está no comando e o user troca na mão, trava o modo —
        # senão a IA reverteria a escolha dele em até 4s. Manual sempre vence.
        auto_override = state["auto"] and not state["mode_locked"]
        if auto_override:
            set_lock(True)
        # feedback de toque: micro-scale
        if modo in chips:
            chips[modo][0].scale = 0.94; page.update()
            threading.Timer(0.12, lambda: (_reset_scale(modo))).start()
        paint_hero(modo); paint_chips(modo)
        set_status(f"{MODE_NAMES[modo]}" + ("  🔒 AUTO pausado" if auto_override else ""), T.WARN)
        worker.send("anc", modo)
        # aprende: escolha manual é o sinal mais forte da preferência (grava local)
        try: um.record(state["ctx_app"], time.localtime().tm_hour, modo)
        except Exception: pass

    def _reset_scale(modo):
        if modo in chips:
            chips[modo][0].scale = 1.0
            try: page.update()
            except Exception: pass

    # ─── bateria + status pill ───
    batt_ring = ft.ProgressRing(width=16, height=16, stroke_width=2, color=T.OK, visible=False)
    batt_text = ft.Text("—", size=13, color=T.WARN, weight=ft.FontWeight.W_700)
    status_dot = ft.Container(width=7, height=7, border_radius=99, bgcolor=T.TXT_FAINT)
    status_lbl = ft.Text(t("starting"), size=11, color=T.TXT_DIM,
                         max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)

    # ─── sparkline de bateria (últimas horas, 100% local) ───
    SPARK_BARS = 24  # nº de barras na sparkline
    batt_spark = ft.Row([], spacing=1, alignment=ft.MainAxisAlignment.END,
                        vertical_alignment=ft.CrossAxisAlignment.END, height=14)
    def paint_batt_spark():
        """Redesenha a sparkline a partir do histórico local. Mostra as últimas
        SPARK_BARS leituras (reamostradas); altura da barra = % da bateria."""
        try:
            vals = blog.series()
        except Exception:
            vals = []
        batt_spark.controls.clear()
        if len(vals) < 2:
            batt_spark.visible = False
            return
        # reamostra pra no máximo SPARK_BARS pontos (pega os mais recentes, espaçados)
        if len(vals) > SPARK_BARS:
            step = len(vals) / SPARK_BARS
            vals = [vals[int(i * step)] for i in range(SPARK_BARS)]
        batt_spark.visible = True
        for v in vals:
            h = max(2, round(v / 100 * 12))  # 2..12 px
            col = T.OK if v > 30 else T.ANC
            batt_spark.controls.append(
                ft.Container(width=3, height=h, bgcolor=col, border_radius=1))

    # ─── Game Mode ───
    game_switch = ft.Switch(value=False, active_color=T.OK, on_change=lambda e: on_game(e))
    def on_game(e):
        on = e.control.value
        mark_touch("game")
        _persist("last_game", on)
        set_status(t("game_on") if on else t("game_off"), T.WARN)
        worker.send("game", 1 if on else 0)

    # ─── Anti-leak (hardware, confirmado) ───
    leak_switch = ft.Switch(value=False, active_color=T.OK, on_change=lambda e: on_leak(e))
    def on_leak(e):
        on = e.control.value
        mark_touch("leak")
        _persist("last_leak", on)
        set_status(t("antileak_on") if on else t("antileak_off"), T.WARN)
        worker.send("leak", 1 if on else 0)

    # ─── EQ APO em CHIPS (software, supre o EQ que o fone não tem) ───
    eq_names = list(wm.EQ_PROFILES.keys())
    eq_state = {"sel": "Padrão"}
    eq_chips = {}
    def make_eq_chip(name):
        c = ft.Container(
            content=ft.Text(t(f"eq_{name}"), size=11, weight=ft.FontWeight.W_600, color=T.TXT,
                            text_align=ft.TextAlign.CENTER),
            padding=ft.Padding.symmetric(vertical=6, horizontal=12),
            border_radius=T.R_PILL, bgcolor=T.SURFACE2,
            border=ft.Border.all(1, T.BORDER), ink=True,
            on_click=lambda e, n=name: on_eq(n),
            animate=ft.Animation(160, ft.AnimationCurve.EASE_OUT),
        )
        eq_chips[name] = c
        return c
    def paint_eq():
        for n, c in eq_chips.items():
            on = (n == eq_state["sel"])
            c.bgcolor = ft.Colors.with_opacity(0.16, T.TRANSP) if on else T.SURFACE2
            c.border = ft.Border.all(1, T.TRANSP if on else T.BORDER)
        page.update()
    def on_eq(name):
        eq_state["sel"] = name
        ok = wm.set_eq_apo(name)
        paint_eq()
        set_status(t("eq_set", name=t(f"eq_{name}")) if ok else t("eq_unavailable"), T.OK if ok else T.ANC)
        c = sysint.load_config(); c["eq"] = name; sysint.save_config(c)
    eq_chips_row = ft.Row([make_eq_chip(n) for n in eq_names], wrap=True, spacing=5, run_spacing=5)

    # ─── Perfis de cenário: 1 clique aplica um combo (modo + game + EQ) ───
    # Reaproveita on_anc/on_game/on_eq (não duplica lógica). EQ só aplica se existir o perfil.
    SCENARIOS = [
        ("sc_focus", ft.Icons.CENTER_FOCUS_STRONG, dict(anc=1, game=False, eq="Vocal")),
        ("sc_game",  ft.Icons.SPORTS_ESPORTS,      dict(anc=0, game=True,  eq="Padrão")),
        ("sc_music", ft.Icons.MUSIC_NOTE,          dict(anc=1, game=False, eq="Padrão")),
        ("sc_call",  ft.Icons.HEADSET_MIC,         dict(anc=2, game=False, eq="Vocal")),
    ]
    def apply_scenario(cfg):
        if cfg.get("anc") is not None:
            on_anc(cfg["anc"])
        if cfg.get("game") is not None:
            mark_touch("game"); game_switch.value = bool(cfg["game"])
            _persist("last_game", bool(cfg["game"]))
            worker.send("game", 1 if cfg["game"] else 0)
        if cfg.get("eq") in wm.EQ_PROFILES:
            on_eq(cfg["eq"])
        try: page.update()
        except Exception: pass
    def make_scenario_chip(label_key, icon, cfg):
        return ft.Container(
            content=ft.Row([ft.Icon(icon, size=14, color=T.TXT),
                            ft.Text(t(label_key), size=11, weight=ft.FontWeight.W_600, color=T.TXT)],
                           spacing=5, tight=True),
            padding=ft.Padding.symmetric(vertical=7, horizontal=12),
            border_radius=T.R_PILL, bgcolor=T.SURFACE2, border=ft.Border.all(1, T.BORDER),
            ink=True, on_click=lambda e, c=cfg: apply_scenario(c),
        )
    scenarios_row = ft.Row([make_scenario_chip(l, i, c) for l, i, c in SCENARIOS],
                           wrap=True, spacing=5, run_spacing=5)

    # ─── Now playing (com equalizer animado) ───
    eq_bars = [ft.Container(width=3, height=h, bgcolor=T.OK, border_radius=2,
                            animate=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT))
               for h in (10, 18, 7, 14)]
    eq_row = ft.Row(eq_bars, spacing=2, alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER)
    np_app = ft.Text("—", size=10, color=T.TXT_FAINT, weight=ft.FontWeight.W_700)
    np_title = ft.Text(t("nothing_playing"), size=13, color=T.TXT, weight=ft.FontWeight.W_600,
                       max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    np_playing = {"v": False}

    def _eq_animator():
        import random
        while True:
            if np_playing["v"]:
                for b in eq_bars:
                    b.height = random.randint(5, 22)
                try: page.update()
                except Exception: pass
            time.sleep(0.32)

    def refresh_now_playing():
        try:
            ss = wm.get_now_playing()
            cur = next((s for s in ss if s["is_current"]), None) or (ss[0] if ss else None)
            if cur and (cur["title"] or cur["artist"]):
                np_app.value = cur["app"].upper()
                txt = cur["title"]
                if cur["artist"]:
                    txt = f"{cur['artist']} — {txt}" if txt else cur["artist"]
                np_title.value = txt or "—"
                np_playing["v"] = cur["playing"]
                for b in eq_bars:
                    b.bgcolor = T.OK if cur["playing"] else T.TXT_FAINT
                    if not cur["playing"]: b.height = 6
            else:
                np_app.value = "—"; np_title.value = "nada tocando"
                np_playing["v"] = False
                for b in eq_bars: b.bgcolor = T.TXT_FAINT; b.height = 6
            page.update()
        except Exception: pass

    def media_btn(icon, action, size=24, primary=False):
        return ft.Container(
            content=ft.Icon(icon, color=T.TXT, size=size),
            width=48 if primary else 40, height=48 if primary else 40,
            border_radius=99, bgcolor=T.SURFACE2 if primary else None,
            alignment=ft.Alignment(0, 0), ink=True,
            on_click=lambda e: (action(), _delayed_np()),
            animate_scale=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
        )
    def _delayed_np(): threading.Timer(0.4, refresh_now_playing).start()

    # ─── Volume ───
    vol_value = ft.Text("—", size=12, color=T.TXT, width=40, weight=ft.FontWeight.W_700)
    vol_state = {"dragging": 0.0}  # timestamp do último arrasto (evita re-sync no meio do gesto)
    def apply_volume(v):
        v = max(0, min(100, int(v)))
        vol_state["dragging"] = time.time()
        wm.set_volume(v); vol_slider.value = v; vol_value.value = f"{v}%"; page.update()
    def sync_volume():
        """Relê o volume REAL do endpoint atual e atualiza a tela. Não mexe se o
        usuário arrastou o slider há <2s (pra não brigar com o gesto). Mantém a tela
        fiel quando o endpoint troca por baixo (A2DP <-> Headset, reconexão)."""
        if time.time() - vol_state["dragging"] < 2.0:
            return
        v = wm.get_volume()
        if v is not None and abs(v - (vol_slider.value or 0)) >= 1:
            vol_slider.value = v; vol_value.value = f"{v}%"
            try: page.update()
            except Exception: pass
    def on_vol_drag(e):
        vol_state["dragging"] = time.time()  # marca: não re-sincronizar agora
        vol_value.value = f"{int(e.control.value)}%"; page.update()
    vol_slider = ft.Slider(min=0, max=100, value=50, expand=True, active_color=T.TRANSP,
                           thumb_color=T.TXT, on_change=on_vol_drag,
                           on_change_end=lambda e: apply_volume(e.control.value))
    def vol_step(d):
        cur = wm.get_volume()
        apply_volume((cur if cur is not None else int(vol_slider.value)) + d)

    # ─── AUTO MODE (IA de contexto) ───
    auto_badge = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.AUTO_AWESOME, color=T.TXT_FAINT, size=16),
            ft.Text("AUTO", size=12, weight=ft.FontWeight.W_800, color=T.TXT_FAINT),
        ], spacing=6, tight=True),
        padding=ft.Padding.symmetric(vertical=8, horizontal=14),
        border_radius=T.R_PILL, bgcolor=T.SURFACE,
        border=ft.Border.all(2, T.SURFACE), ink=True,
        on_click=lambda e: toggle_auto(),
        animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        tooltip=t("auto_hint"),
    )
    auto_hint = ft.Text("", size=10, color=T.OK, italic=True)

    def paint_auto():
        on = state["auto"]
        auto_badge.bgcolor = ft.Colors.with_opacity(0.13, T.OK) if on else T.SURFACE
        auto_badge.border = ft.Border.all(2, T.OK if on else T.SURFACE)
        auto_badge.content.controls[0].color = T.OK if on else T.TXT_FAINT
        auto_badge.content.controls[1].color = T.OK if on else T.TXT_FAINT
        auto_hint.value = "" if on else ""
        page.update()

    def toggle_auto():
        state["auto"] = not state["auto"]
        paint_auto()
        if state["auto"]:
            if state["mode_locked"]:
                set_lock(False)  # ligar a IA destrava o modo (o user quer ela no comando)
            set_status(t("auto_on"), T.OK)
            threading.Thread(target=lambda: _auto_tick(force=True), daemon=True).start()
        else:
            set_status(t("auto_off"), T.TXT_DIM)

    def _auto_tick(force=False):
        """aplica o modo sugerido pelo contexto (se AUTO ligado e o modo não estiver travado)"""
        if not state["auto"] or state["mode_locked"]:
            return
        try:
            modo, game, motivo = ce.suggest_mode()
            # overlay do mapa de uso local: se você tem um hábito claro nesse
            # app + período, a SUA preferência vence a heurística genérica
            learned = um.predict(state["ctx_app"], time.localtime().tm_hour)
            if learned:
                lmode, share, _total = learned
                modo = lmode
                motivo = f"você costuma usar {MODE_NAMES[lmode]} aqui ({int(share*100)}%)"
            if modo is not None and (force or modo != state["last_auto"]):
                state["last_auto"] = modo
                state["mode"] = modo
                paint_hero(modo); paint_chips(modo)
                auto_hint.value = f"🤖 {motivo} → {MODE_NAMES[modo]}"
                set_status(f"AUTO: {MODE_NAMES[modo]} ({motivo})", T.OK)
                worker.send("anc", modo)
                if game and not state["game"]:
                    game_switch.value = True; state["game"] = True
                    worker.send("game", 1); page.update()
        except Exception:
            pass

    def _auto_loop():
        while True:
            time.sleep(4)
            if state["auto"]:
                _auto_tick()

    # rastreia o último app REAL em foco (ignora a janela do próprio Haylou) pra o
    # aprendizado saber em que app você estava quando trocou de modo
    SELF_PROCS = ("haylou", "python", "pythonw", "flet", "applicationframehost")
    def _ctx_sampler():
        while True:
            try:
                p = ce.get_foreground_process()
                if p and not any(s in p for s in SELF_PROCS):
                    state["ctx_app"] = p
            except Exception:
                pass
            time.sleep(2)

    # ─── callbacks thread-safe ───
    def set_status(text, color=T.TXT_DIM):
        status_lbl.value = text; status_lbl.color = color; status_dot.bgcolor = color
        try: page.update()
        except Exception: pass
    def set_batt(pct):
        state["batt"] = pct
        batt_text.value = f"{pct}%"
        batt_text.color = T.OK if pct > 30 else T.ANC
        try: blog.record(pct); paint_batt_spark()  # histórico + sparkline
        except Exception: pass
        try: page.update()
        except Exception: pass
        # atualiza o tooltip do tray com a bateria nova
        try: sysint.update_tray_mode(tray["icon"], state["mode"],
                                     get_mode=lambda: state["mode"], get_batt=lambda: state["batt"])
        except Exception: pass
    def set_mode_from_device(modo):
        if is_locked("anc"): return  # user acabou de trocar — não sobrescreve
        state["mode"] = modo
        paint_hero(modo); paint_chips(modo)
    def set_game_from_device(on):
        if is_locked("game"): return  # user mexeu agora — não sobrescreve
        state["game"] = on; game_switch.value = on
        try: page.update()
        except Exception: pass
    def set_leak_from_device(on):
        if is_locked("leak"): return
        leak_switch.value = on
        try: page.update()
        except Exception: pass

    # ─── LAYOUT ───
    img_path = os.path.join(os.path.dirname(__file__), "assets", "s30.png")

    def section(title, *content):
        return ft.Container(
            content=ft.Column([
                ft.Text(title.upper(), size=10, color=T.TXT_FAINT, weight=ft.FontWeight.W_700),
                *content,
            ], spacing=8),
            padding=12, border_radius=T.R_CARD, bgcolor=T.SURFACE,
        )

    # ─── Onboarding banner (1ª vez) ───
    cfg0 = sysint.load_config()
    onboard_banner = ft.Container(
        visible=not cfg0.get("onboarded", False),
        content=ft.Row([
            ft.Icon(ft.Icons.TIPS_AND_UPDATES, color=T.WARN, size=18),
            ft.Text(t("onboard"), size=11, color=T.TXT_DIM, expand=True),
            ft.Container(content=ft.Icon(ft.Icons.CLOSE, color=T.TXT_FAINT, size=16),
                         ink=True, on_click=lambda e: dismiss_onboard(), padding=4, border_radius=99),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(vertical=10, horizontal=14),
        border_radius=12, bgcolor=ft.Colors.with_opacity(0.10, T.WARN),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.28, T.WARN)),
    )
    def dismiss_onboard():
        onboard_banner.visible = False
        c = sysint.load_config(); c["onboarded"] = True; sysint.save_config(c)
        page.update()

    # ─── Banner de atualização disponível (preenchido pelo check em background) ───
    import webbrowser
    update_lbl = ft.Text("", size=11, color=T.TXT, expand=True, weight=ft.FontWeight.W_600)
    update_banner = ft.Container(
        visible=False,
        content=ft.Row([
            ft.Icon(ft.Icons.SYSTEM_UPDATE, color=T.OK, size=18),
            update_lbl,
            ft.Container(content=ft.Icon(ft.Icons.CLOSE, color=T.TXT_FAINT, size=16),
                         ink=True, on_click=lambda e: _dismiss_update(), padding=4, border_radius=99),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(vertical=10, horizontal=14),
        border_radius=12, bgcolor=ft.Colors.with_opacity(0.10, T.OK),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.28, T.OK)),
        ink=True, on_click=lambda e: webbrowser.open(updater.RELEASES_PAGE),
        tooltip="Abrir a página de download",
    )
    def _dismiss_update():
        update_banner.visible = False
        page.update()

    # ─── botão settings (auto-start) ───
    autostart_on = {"v": sysint.is_autostart_enabled()}
    def toggle_autostart(e):
        autostart_on["v"] = not autostart_on["v"]
        ok = sysint.set_autostart(autostart_on["v"])
        settings_btn.icon_color = T.OK if (autostart_on["v"] and ok) else T.TXT_FAINT
        set_status(t("autostart_set", on="ON" if autostart_on["v"] else "OFF"), T.OK)
        page.update()
    settings_btn = ft.IconButton(ft.Icons.ROCKET_LAUNCH, icon_size=18,
                                 icon_color=T.OK if autostart_on["v"] else T.TXT_FAINT,
                                 tooltip=t("autostart_tip"), on_click=toggle_autostart)

    # ─── TEMA dark ⇄ light (toggle instantâneo) ───
    # Recolor por varredura: troca SÓ as cores do tema na árvore já montada — não
    # relança o app, não rebuilda a UI. Cores de accent (ANC/TRANSP) ficam intactas.
    def _iter_controls(items):
        for c in items:
            if not isinstance(c, ft.Control):
                continue
            yield c
            ct = getattr(c, "content", None)
            if isinstance(ct, ft.Control):
                yield from _iter_controls([ct])
            sub = getattr(c, "controls", None)
            if isinstance(sub, (list, tuple)):
                yield from _iter_controls(sub)

    _COLOR_ATTRS = ("color", "bgcolor", "icon_color", "active_color",
                    "thumb_color", "active_track_color")

    def _reborder(b, trans):
        """Recria o ft.Border com as cores remapeadas (objeto NOVO — mutar in-place
        não dispara re-render no Flet). Retorna None se não for um Border."""
        if not isinstance(b, ft.Border):
            return None
        def _side(s):
            col = getattr(s, "color", None) if s is not None else None
            if isinstance(col, str) and col.upper() in trans:
                return ft.BorderSide(getattr(s, "width", 1) or 1, trans[col.upper()])
            return s
        return ft.Border(left=_side(b.left), top=_side(b.top),
                         right=_side(b.right), bottom=_side(b.bottom))

    def set_theme(name):
        old = {k: getattr(T, k) for k in THEMED_KEYS}
        apply_palette(name)
        trans = {old[k].upper(): getattr(T, k) for k in THEMED_KEYS}
        for c in _iter_controls(page.controls):
            try:  # um controle problemático não pode abortar a varredura toda
                for a in _COLOR_ATTRS:
                    v = getattr(c, a, None)
                    if isinstance(v, str) and v.upper() in trans:
                        setattr(c, a, trans[v.upper()])
                nb = _reborder(getattr(c, "border", None), trans)
                if nb is not None:
                    c.border = nb  # reatribui objeto novo → Flet re-renderiza a borda
            except Exception:
                pass
        # re-aplica estados dinâmicos (bordas/tints de seleção) com a paleta nova
        try:
            paint_chips(state["mode"]); paint_eq(); paint_auto()
        except Exception:
            pass
        page.bgcolor = T.BG
        page.theme_mode = ft.ThemeMode.LIGHT if name == "light" else ft.ThemeMode.DARK
        cfg_t = sysint.load_config(); cfg_t["theme"] = name; sysint.save_config(cfg_t)
        is_dark = (name != "light")
        theme_btn.icon = ft.Icons.LIGHT_MODE if is_dark else ft.Icons.DARK_MODE
        theme_btn.tooltip = t("theme_light") if is_dark else t("theme_dark")
        set_status(t("theme_light_set") if not is_dark else t("theme_dark_set"), T.TXT_DIM)
        page.update()

    def toggle_theme(e):
        cur = sysint.load_config().get("theme", "dark")
        set_theme("light" if cur == "dark" else "dark")
    theme_btn = ft.IconButton(
        ft.Icons.LIGHT_MODE if _theme != "light" else ft.Icons.DARK_MODE,
        icon_size=18, icon_color=T.TXT_DIM,
        tooltip=t("theme_light") if _theme != "light" else t("theme_dark"),
        on_click=toggle_theme)

    # ─── botão de idioma (PT ⇄ EN) ───
    # Salva o novo idioma e REINICIA o processo limpo (re-exec do mesmo .exe). Recriar a
    # UI no mesmo processo duplicaria worker BLE / hotkeys / threads — re-exec é o jeito
    # seguro de reaplicar a tradução sem deixar lixo rodando.
    def toggle_lang(e=None):
        new = "en" if i18n.get_lang() == "pt" else "pt"
        c = sysint.load_config(); c["lang"] = new; sysint.save_config(c)
        # NÃO reinicia sozinho (re-exec do onefile dava erro de DLL). Avisa pra reabrir.
        i18n.set_lang(new)  # aplica já pros próximos textos/notificações
        msg = ("Idioma alterado — feche e abra o app pra aplicar"
               if new == "pt" else "Language changed — close and reopen the app to apply")
        set_status(msg, T.WARN)
        try: sysint.notify("Haylou S30 Pro", msg)
        except Exception: pass
    lang_btn = ft.IconButton(ft.Icons.TRANSLATE, icon_size=18, icon_color=T.TXT_DIM,
                             tooltip=t("lang_tip"), on_click=toggle_lang)

    # ─── botão reconectar (força nova conexão BLE na hora) ───
    def do_reconnect(e=None):
        set_status(t("reconnecting"), T.WARN)
        worker.send("force_reconnect")
    reconnect_btn = ft.IconButton(ft.Icons.REFRESH, icon_size=18, icon_color=T.TXT_DIM,
                                  tooltip=t("reconnect_tip"), on_click=do_reconnect)

    # ─── helpers de dialog (Flet 0.85: overlay + open flag) ───
    def _show_dialog(dlg):
        if dlg not in page.overlay:
            page.overlay.append(dlg)
        dlg.open = True; page.update()
    def _close_dialog(dlg):
        dlg.open = False; page.update()

    # ─── ESTATÍSTICAS de uso (do aprendizado local) ───
    def open_stats(e=None):
        try: s = um.summary()
        except Exception: s = {"total": 0, "by_mode": {}, "top_apps": []}
        rows = []
        if s["total"] == 0:
            rows.append(ft.Text(t("stats_empty"), size=12, color=T.TXT_DIM))
        else:
            rows.append(ft.Text(t("stats_total", n=s["total"]), size=11, color=T.TXT_FAINT))
            for nome, n in s["by_mode"].items():
                pct = round(n / s["total"] * 100) if s["total"] else 0
                rows.append(ft.Row([
                    ft.Text(nome, size=12, color=T.TXT, width=110),
                    ft.Container(height=8, width=max(4, pct * 1.6), bgcolor=T.TRANSP, border_radius=4),
                    ft.Text(f"{pct}%", size=11, color=T.TXT_DIM),
                ], spacing=8))
            if s["top_apps"]:
                rows.append(ft.Text(t("stats_top_apps"), size=11,
                                    color=T.TXT_FAINT, weight=ft.FontWeight.W_700))
                for app, pref, n in s["top_apps"]:
                    rows.append(ft.Text(f"• {app} → {um.MODE_LABELS.get(pref,'?')} ({n}x)",
                                        size=12, color=T.TXT))
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(t("stats_title")),
            content=ft.Column(rows, tight=True, spacing=8, width=360, scroll=ft.ScrollMode.AUTO),
            actions=[ft.TextButton(t("close"), on_click=lambda ev: _close_dialog(dlg))],
        )
        _show_dialog(dlg)
    stats_btn = ft.IconButton(ft.Icons.INSIGHTS, icon_size=18, icon_color=T.TXT_DIM,
                              tooltip=t("stats_tip"), on_click=open_stats)

    root = ft.Container(
        opacity=0,  # fade-in na abertura
        animate_opacity=ft.Animation(400, ft.AnimationCurve.EASE_OUT),
        content=ft.Column([
            # banners (update disponível / dica de 1ª vez) — escondidos por padrão
            update_banner,
            onboard_banner,
            # topbar: foto + nome + bateria/status + settings
            ft.Row([
                ft.Image(src=img_path, width=46, height=46, fit=ft.BoxFit.CONTAIN),
                ft.Column([
                    ft.Text("Haylou S30 Pro", size=16, weight=ft.FontWeight.W_800, color=T.TXT),
                    ft.Row([status_dot, status_lbl], spacing=6, tight=True),
                ], spacing=2, expand=True, tight=True),
                ft.Column([
                    ft.Row([ft.Icon(ft.Icons.BATTERY_FULL, color=T.WARN, size=16), batt_text],
                           spacing=3, tight=True),
                    batt_spark,  # sparkline da bateria (últimas horas)
                    ft.Row([lang_btn, stats_btn, reconnect_btn, theme_btn, settings_btn], spacing=0, tight=True),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.END, tight=True),
            ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),

            # linha AUTO (heurística local de contexto)
            ft.Row([auto_badge, auto_hint], spacing=10,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),

            # perfis de cenário (presets de 1 clique)
            scenarios_row,

            hero,

            # chips de modo
            ft.Row([make_chip(n, m, c, i, d) for n, m, c, i, d in anc_modes()],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

            # game mode
            ft.Container(
                content=ft.Row([
                    ft.Row([ft.Icon(ft.Icons.SPORTS_ESPORTS, color=T.TXT_DIM, size=20),
                            ft.Column([
                                ft.Text(t("game_mode"), size=13, color=T.TXT, weight=ft.FontWeight.W_600),
                                ft.Text(t("low_latency"), size=10, color=T.TXT_FAINT),
                            ], spacing=0, tight=True)], spacing=12),
                    game_switch,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=ft.Padding.symmetric(vertical=9, horizontal=14),
                border_radius=T.R_CARD, bgcolor=T.SURFACE,
            ),

            # ─── ÁUDIO DO PC (EQ + anti-leak + spatial) ───
            section(t("audio"),
                ft.Column([
                    ft.Text(t("pc_eq"), size=13, color=T.TXT, weight=ft.FontWeight.W_600),
                    ft.Text(t("pc_eq_desc"), size=10, color=T.TXT_FAINT),
                    eq_chips_row,
                ], spacing=8, tight=True),
                ft.Row([
                    ft.Column([
                        ft.Text(t("antileak"), size=13, color=T.TXT, weight=ft.FontWeight.W_600),
                        ft.Text(t("antileak_desc"), size=10, color=T.TXT_FAINT),
                    ], spacing=0, tight=True, expand=True),
                    leak_switch,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.SURROUND_SOUND, color=T.TRANSP, size=18),
                        ft.Text(t("spatial"), size=12, color=T.TRANSP, weight=ft.FontWeight.W_600),
                    ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
                    on_click=lambda e: wm.toggle_spatial_panel(), ink=True,
                    padding=ft.Padding.symmetric(vertical=8, horizontal=0), border_radius=10,
                    tooltip=t("spatial_tip"),
                ),
            ),

            # tocando agora + controles
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Container(content=eq_row, width=26, height=26, alignment=ft.Alignment(0, 0)),
                        ft.Column([np_app, np_title], spacing=1, expand=True, tight=True),
                    ], spacing=10),
                    ft.Row([
                        media_btn(ft.Icons.SKIP_PREVIOUS, wm.prev_track),
                        media_btn(ft.Icons.PLAY_ARROW, wm.play_pause, size=30, primary=True),
                        media_btn(ft.Icons.SKIP_NEXT, wm.next_track),
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=14),
                    ft.Row([
                        ft.Container(content=ft.Icon(ft.Icons.REMOVE, color=T.TXT_DIM, size=18),
                                     width=30, height=30, border_radius=99, ink=True,
                                     alignment=ft.Alignment(0, 0), on_click=lambda e: vol_step(-5)),
                        vol_slider,
                        ft.Container(content=ft.Icon(ft.Icons.ADD, color=T.TXT_DIM, size=18),
                                     width=30, height=30, border_radius=99, ink=True,
                                     alignment=ft.Alignment(0, 0), on_click=lambda e: vol_step(5)),
                        vol_value,
                    ], spacing=2),
                ], spacing=8),
                padding=12, border_radius=T.R_CARD, bgcolor=T.SURFACE,
            ),
        ], spacing=9),
        padding=ft.Padding.symmetric(vertical=12, horizontal=16),
    )

    page.add(root)
    # restaura o ÚLTIMO estado salvo (modo/game/leak) — só visual. O fone confirma
    # quando conectar; se estiver desconectado, o usuário vê o que deixou da última vez.
    _last_anc = cfg0.get("last_anc", 1)
    state["mode"] = _last_anc if _last_anc in (0, 1, 2) else 1
    game_switch.value = bool(cfg0.get("last_game", False))
    leak_switch.value = bool(cfg0.get("last_leak", False))
    paint_hero(state["mode"]); paint_chips(state["mode"])

    # fade-in
    def _fade():
        time.sleep(0.05); root.opacity = 1;
        try: page.update()
        except Exception: pass
    threading.Thread(target=_fade, daemon=True).start()

    # volume inicial
    try:
        v = wm.get_volume()
        if v is not None: vol_slider.value = v; vol_value.value = f"{v}%"; page.update()
    except Exception: pass

    # now playing + equalizer + poller
    refresh_now_playing()
    threading.Thread(target=_eq_animator, daemon=True).start()
    def _np_poller():
        while True:
            time.sleep(5); refresh_now_playing(); sync_volume()
    threading.Thread(target=_np_poller, daemon=True).start()

    # loop da IA de contexto (AUTO) + rastreador de app em foco (alimenta o aprendizado)
    paint_auto()
    threading.Thread(target=_auto_loop, daemon=True).start()
    threading.Thread(target=_ctx_sampler, daemon=True).start()

    # ─── verifica atualização no GitHub (background, silencioso se offline) ───
    def _check_update():
        time.sleep(3)  # não atrasa a abertura
        try:
            has_new, tag = updater.check()
            if has_new:
                update_banner.visible = True
                update_lbl.value = t("update_avail", tag=tag)
                page.update()
        except Exception: pass
    threading.Thread(target=_check_update, daemon=True).start()

    # ─── PERSISTÊNCIA: restaura último EQ salvo (chips já salvam no on_eq) ───
    cfg = sysint.load_config()
    if cfg.get("eq") in wm.EQ_PROFILES:
        eq_state["sel"] = cfg["eq"]; wm.set_eq_apo(cfg["eq"]); paint_eq()

    # watcher: se o Equalizer APO resetar o config por fora (troca de dispositivo,
    # update), reaplica o perfil ativo sozinho
    if wm.eq_apo_available():
        wm.watch_eq_apo(lambda: eq_state["sel"],
                        on_reapply=lambda n: set_status(f"EQ reaplicado: {n}", T.OK))

    # BLE worker — endereço vem do config (multi-fone); lembra o fone ao conectar
    def _save_device(addr, name):
        c = sysint.load_config(); c["device_addr"] = addr
        if name: c["device_name"] = name
        sysint.save_config(c)
    global worker
    worker = BleWorker(set_status, set_batt, set_mode_from_device,
                       set_game_from_device, set_leak_from_device,
                       addr=cfg.get("device_addr"), on_device=_save_device)

    # ─── NOTIFICAÇÃO de bateria baixa: avisa 1x ao cruzar 20% (baixa) e 1x ao cruzar
    #     10% (crítica). Rearma quando recarrega acima de 30%. ───
    batt_warned = {"low": False, "crit": False}
    _orig_set_batt = set_batt
    def set_batt(pct):
        _orig_set_batt(pct)
        if pct <= 10 and not batt_warned["crit"]:
            batt_warned["crit"] = True; batt_warned["low"] = True
            sysint.notify("Haylou S30 Pro", t("batt_crit", pct=pct))
        elif pct <= 20 and not batt_warned["low"]:
            batt_warned["low"] = True
            sysint.notify("Haylou S30 Pro", t("batt_low", pct=pct))
        elif pct > 30:
            batt_warned["low"] = False; batt_warned["crit"] = False
    worker.on_batt = set_batt  # reaponta pro wrapper

    # ─── HOTKEYS GLOBAIS ───
    # Ctrl+Alt+A cicla ANC→Transparência→Normal. Atalhos diretos pra cada modo e Game,
    # pra trocar de qualquer lugar sem ciclar. Falha de uma não impede as outras.
    def cycle_anc():
        nxt = {1: 2, 2: 0, 0: 1}.get(state["mode"], 1)
        on_anc(nxt)
    def toggle_game_hotkey():
        new = not game_switch.value
        game_switch.value = new
        on_game(type("E", (), {"control": game_switch})())  # reusa o handler real
    sysint.register_hotkey("ctrl+alt+a", cycle_anc)
    sysint.register_hotkey("ctrl+alt+1", lambda: on_anc(1))  # ANC
    sysint.register_hotkey("ctrl+alt+2", lambda: on_anc(2))  # Transparência
    sysint.register_hotkey("ctrl+alt+0", lambda: on_anc(0))  # Normal
    sysint.register_hotkey("ctrl+alt+g", toggle_game_hotkey)  # Game on/off

    # ─── SYSTEM TRAY: menu rápido (clicar abre, ações trocam modo) ───
    def show_window():
        try:
            page.window.visible = True
            page.window.minimized = False
            page.window.to_front(); page.update()
        except Exception: pass
    def quit_app():
        import os as _os; _os._exit(0)

    # ─── fechar (X) esconde pro tray em vez de encerrar (sair = menu do tray) ───
    # Na 1ª vez avisa que continua no tray (senão parece que travou). Depois fica quieto.
    def hide_window():
        try:
            page.window.visible = False; page.update()
        except Exception: pass
        c = sysint.load_config()
        if not c.get("tray_hint_shown"):
            c["tray_hint_shown"] = True; sysint.save_config(c)
            try:
                sysint.notify("Haylou S30 Pro",
                              t("tray_hint") if i18n else "Continua rodando na bandeja. Clique no ícone pra abrir; botão direito → Sair.")
            except Exception: pass
    def _on_window_event(e):
        if e.data == "close":
            hide_window()
    page.window.on_event = _on_window_event

    try:
        tray["icon"] = sysint.make_tray(
            on_show=show_window,
            on_anc=lambda: on_anc(1),
            on_transp=lambda: on_anc(2),
            on_normal=lambda: on_anc(0),
            on_quit=quit_app,
            get_mode=lambda: state["mode"],
            get_batt=lambda: state["batt"],     # bateria no tooltip
            on_cycle=cycle_anc,                  # clique no ícone cicla o ANC
        )
    except Exception:
        pass  # tray é bônus — se falhar, app segue normal


if __name__ == "__main__":
    # trava de instância única: se já há uma janela aberta, foca ela e sai
    # (evita 2+ cópias brigando pela única conexão BLE)
    if not sysint.acquire_single_instance():
        sysint.focus_existing_window("Haylou S30 Pro")
        sys.exit(0)
    try:
        ft.run(main)
    finally:
        sys.stderr = open(os.devnull, "w")
        os._exit(0)
