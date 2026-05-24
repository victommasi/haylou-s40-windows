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
import flet as ft
from bleak import BleakClient, BleakScanner
import winmedia as wm
import haylou_protocol as proto
import context_engine as ce
import system_integration as sysint

CF_WRITE  = "0000cf05-0000-1000-8000-00805f9b34fb"
CF_NOTIFY = "0000cf06-0000-1000-8000-00805f9b34fb"
ADDR_HINTS = ("BB:AD:EE",)  # OUI da Haylou — usado pra achar o fone no scan
# vazio = procura qualquer fone Haylou no scan. O endereço real do SEU fone é
# descoberto e salvo no config.json na 1ª conexão (não vem chumbado no código).
KNOWN_ADDR = ""

# ═══════════════════ DESIGN TOKENS ═══════════════════
class T:
    # superfícies
    BG       = "#08080F"
    SURFACE  = "#13131F"
    SURFACE2 = "#1B1B2A"
    BORDER   = "#26263A"
    # texto
    TXT      = "#FFFFFF"
    TXT_DIM  = "#8B8B9E"
    TXT_FAINT= "#5A5A6E"
    # accent / semântico
    ANC      = "#FF3B5C"
    TRANSP   = "#3B82F6"
    NORMAL   = "#64748B"
    OK       = "#22D67B"
    WARN     = "#FBBF24"
    # raios / espaços
    R_CARD   = 18
    R_PILL   = 999
    # tipografia
    F = "Segoe UI"

ANC_MODES = [
    ("ANC",            1, T.ANC,    ft.Icons.NOISE_CONTROL_OFF, "Cancelamento de ruído"),
    ("Transparência",  2, T.TRANSP, ft.Icons.HEARING,           "Ouve o ambiente"),
    ("Normal",         0, T.NORMAL, ft.Icons.MUSIC_NOTE,        "Sem processamento"),
]
MODE_NAMES = {0:"Normal",1:"ANC",2:"Transparência"}
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
        threading.Thread(target=lambda: asyncio.run(self._loop()), daemon=True).start()

    def send(self, kind, value=None): self.q.put((kind, value))

    async def _connect(self):
        if self.client and self.client.is_connected: return True
        self.on_status("conectando", T.WARN)
        # 1) tenta o endereço conhecido (config/1ª conexão). Se vazio, vai direto pro scan.
        if self.addr:
            try:
                self.client = BleakClient(self.addr, timeout=6.0)
                await self.client.connect()
                if self.client.is_connected:
                    await self.client.start_notify(CF_NOTIFY, self._notify)
                    self.on_status("conectado", T.OK); return True
            except Exception: pass
        # fallback: escaneia e conecta no 1º fone Haylou (e lembra o endereço)
        try:
            for d in await BleakScanner.discover(timeout=4.0):
                if d.address.upper().startswith(ADDR_HINTS):
                    self.client = BleakClient(d.address, timeout=6.0)
                    await self.client.connect()
                    if self.client.is_connected:
                        await self.client.start_notify(CF_NOTIFY, self._notify)
                        self.addr = d.address
                        if self.on_device:
                            try: self.on_device(d.address, getattr(d, "name", None))
                            except Exception: pass
                        self.on_status("conectado", T.OK); return True
        except Exception: pass
        self.on_status("fone offline", T.ANC); return False

    def _notify(self, _, data):
        b = bytes(data)
        pct = proto.parse_battery(b)
        if pct is not None: self.on_batt(pct)
        if self.on_mode:
            m = proto.parse_anc_mode(b)
            if m is not None: self.on_mode(m)
        if self.on_game:
            g = proto.parse_game_mode(b)
            if g is not None: self.on_game(g)
        if self.on_leak:
            lk = proto.parse_attr(b, proto.ORD_LEAK)
            if lk in (0, 1): self.on_leak(bool(lk))

    async def _poll_battery(self):
        while True:
            await asyncio.sleep(30); self.q.put(("status", None))

    async def _loop(self):
        await self._connect(); await self._status()
        asyncio.create_task(self._poll_battery())
        while True:
            kind, value = await asyncio.get_event_loop().run_in_executor(None, self.q.get)
            if kind == "quit": break
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
    page.title = "Haylou S30 Pro"
    page.window.width = 400
    page.window.height = 880
    page.window.resizable = False
    page.window.title_bar_hidden = False
    page.bgcolor = T.BG
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO  # rola quando o conteúdo passa da altura da janela
    page.theme_mode = ft.ThemeMode.DARK
    page.fonts = {}

    state = {"mode": 1, "batt": None, "game": False, "auto": False, "last_auto": None}
    tray = {"icon": None}  # ícone da bandeja (atualiza com o modo)

    # lock de interação: quando o user mexe num controle, ignora updates do device
    # por LOCK_MS (evita notify atrasado reverter o que o user acabou de fazer)
    LOCK_MS = 5.0
    touched = {}
    def mark_touch(name): touched[name] = time.time()
    def is_locked(name): return (time.time() - touched.get(name, 0)) < LOCK_MS

    state["mode_locked"] = False  # cadeado: trava o modo (AUTO não mexe)

    # ─── HERO: card grande do modo ativo (com glow + cadeado de override) ───
    hero_icon = ft.Icon(MODE_ICON[1], color=T.TXT, size=40)
    hero_name = ft.Text("ANC", size=24, weight=ft.FontWeight.W_800, color=T.TXT)
    hero_desc = ft.Text("Cancelamento de ruído", size=12, color="#FFFFFF", opacity=0.7)
    hero_lock = ft.Container(
        content=ft.Icon(ft.Icons.LOCK_OPEN, color="#FFFFFF", size=20),
        ink=True, on_click=lambda e: toggle_lock(), padding=6, border_radius=99,
        tooltip="Travar o modo (impede a IA de trocar)",
        opacity=0.6,
    )
    hero = ft.Container(
        content=ft.Row([
            hero_icon,
            ft.Column([hero_name, hero_desc], spacing=1, tight=True, expand=True),
            hero_lock,
        ], spacing=16, alignment=ft.MainAxisAlignment.START,
           vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(vertical=22, horizontal=24),
        border_radius=T.R_CARD,
        bgcolor=T.ANC,
        shadow=ft.BoxShadow(blur_radius=32, spread_radius=-6, color=T.ANC, offset=ft.Offset(0, 8)),
        animate=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
    )

    def set_lock(on):
        """Liga/desliga o cadeado do modo. Travado = a IA (AUTO) não troca o modo."""
        state["mode_locked"] = on
        hero_lock.content.name = ft.Icons.LOCK if on else ft.Icons.LOCK_OPEN
        hero_lock.content.color = T.WARN if on else "#FFFFFF"
        hero_lock.opacity = 1.0 if on else 0.6
        try: page.update()
        except Exception: pass

    def toggle_lock():
        set_lock(not state["mode_locked"])
        set_status("Modo travado — a IA não troca mais" if state["mode_locked"] else "Modo destravado",
                   T.WARN if state["mode_locked"] else T.TXT_DIM)

    def paint_hero(modo):
        c = MODE_COLOR[modo]
        hero.bgcolor = c
        hero.shadow = ft.BoxShadow(blur_radius=34, spread_radius=-6, color=c, offset=ft.Offset(0, 8))
        hero_icon.name = MODE_ICON[modo]
        hero_name.value = MODE_NAMES[modo]
        hero_desc.value = next((d for n,m,col,i,d in ANC_MODES if m==modo), "")
        sysint.update_tray_mode(tray["icon"], modo)  # reflete o modo no ícone da bandeja
        page.update()

    # ─── chips de modo (compactos, abaixo do hero) ───
    chips = {}
    def make_chip(name, modo, color, icon, desc):
        chip = ft.Container(
            content=ft.Column([
                ft.Icon(icon, color=T.TXT, size=22),
                ft.Text(name, size=11, weight=ft.FontWeight.W_600, color=T.TXT,
                        text_align=ft.TextAlign.CENTER),
            ], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
            width=104, height=78, border_radius=14,
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
            chip.bgcolor = (color + "26") if on else T.SURFACE  # +26 = alpha leve
        page.update()

    def on_anc(modo):
        state["mode"] = modo
        mark_touch("anc")
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

    def _reset_scale(modo):
        if modo in chips:
            chips[modo][0].scale = 1.0
            try: page.update()
            except Exception: pass

    # ─── bateria + status pill ───
    batt_ring = ft.ProgressRing(width=16, height=16, stroke_width=2, color=T.OK, visible=False)
    batt_text = ft.Text("—", size=13, color=T.WARN, weight=ft.FontWeight.W_700)
    status_dot = ft.Container(width=7, height=7, border_radius=99, bgcolor=T.TXT_FAINT)
    status_lbl = ft.Text("iniciando", size=11, color=T.TXT_DIM)

    # ─── Game Mode ───
    game_switch = ft.Switch(value=False, active_color=T.OK, on_change=lambda e: on_game(e))
    def on_game(e):
        on = e.control.value
        mark_touch("game")
        set_status(f"Game Mode {'ON' if on else 'OFF'}", T.WARN)
        worker.send("game", 1 if on else 0)

    # ─── Anti-leak (hardware, confirmado) ───
    leak_switch = ft.Switch(value=False, active_color=T.OK, on_change=lambda e: on_leak(e))
    def on_leak(e):
        on = e.control.value
        mark_touch("leak")
        set_status(f"Anti-vazamento {'ON' if on else 'OFF'}", T.WARN)
        worker.send("leak", 1 if on else 0)

    # ─── EQ APO em CHIPS (software, supre o EQ que o fone não tem) ───
    eq_names = list(wm.EQ_PROFILES.keys())
    eq_state = {"sel": "Padrão"}
    eq_chips = {}
    def make_eq_chip(name):
        c = ft.Container(
            content=ft.Text(name, size=11, weight=ft.FontWeight.W_600, color=T.TXT,
                            text_align=ft.TextAlign.CENTER),
            padding=ft.Padding.symmetric(vertical=8, horizontal=12),
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
            c.bgcolor = (T.TRANSP + "26") if on else T.SURFACE2
            c.border = ft.Border.all(1, T.TRANSP if on else T.BORDER)
        page.update()
    def on_eq(name):
        eq_state["sel"] = name
        ok = wm.set_eq_apo(name)
        paint_eq()
        set_status(f"EQ: {name}" if ok else "EQ APO indisponível", T.OK if ok else T.ANC)
        c = sysint.load_config(); c["eq"] = name; sysint.save_config(c)
    eq_chips_row = ft.Row([make_eq_chip(n) for n in eq_names], wrap=True, spacing=6, run_spacing=6)

    # ─── Now playing (com equalizer animado) ───
    eq_bars = [ft.Container(width=3, height=h, bgcolor=T.OK, border_radius=2,
                            animate=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT))
               for h in (10, 18, 7, 14)]
    eq_row = ft.Row(eq_bars, spacing=2, alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER)
    np_app = ft.Text("—", size=10, color=T.TXT_FAINT, weight=ft.FontWeight.W_700)
    np_title = ft.Text("nada tocando", size=13, color=T.TXT, weight=ft.FontWeight.W_600,
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
    def apply_volume(v):
        v = max(0, min(100, int(v)))
        wm.set_volume(v); vol_slider.value = v; vol_value.value = f"{v}%"; page.update()
    def on_vol_drag(e):
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
        tooltip="IA escolhe o modo pelo contexto (música→ANC, call→Transparência, jogo→Game)",
    )
    auto_hint = ft.Text("", size=10, color=T.OK, italic=True)

    def paint_auto():
        on = state["auto"]
        auto_badge.bgcolor = (T.OK + "22") if on else T.SURFACE
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
            set_status("AUTO ligado — IA no comando", T.OK)
            threading.Thread(target=lambda: _auto_tick(force=True), daemon=True).start()
        else:
            set_status("AUTO desligado — manual", T.TXT_DIM)

    def _auto_tick(force=False):
        """aplica o modo sugerido pelo contexto (se AUTO ligado e o modo não estiver travado)"""
        if not state["auto"] or state["mode_locked"]:
            return
        try:
            modo, game, motivo = ce.suggest_mode()
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

    # ─── callbacks thread-safe ───
    def set_status(text, color=T.TXT_DIM):
        status_lbl.value = text; status_lbl.color = color; status_dot.bgcolor = color
        try: page.update()
        except Exception: pass
    def set_batt(pct):
        batt_text.value = f"{pct}%"
        batt_text.color = T.OK if pct > 30 else T.ANC
        try: page.update()
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
            ], spacing=10),
            padding=16, border_radius=T.R_CARD, bgcolor=T.SURFACE,
        )

    # ─── Onboarding banner (1ª vez) ───
    cfg0 = sysint.load_config()
    onboard_banner = ft.Container(
        visible=not cfg0.get("onboarded", False),
        content=ft.Row([
            ft.Icon(ft.Icons.TIPS_AND_UPDATES, color=T.WARN, size=18),
            ft.Text("Dica: liga o AUTO e a IA troca o modo sozinha. Ctrl+Alt+A cicla o ANC de qualquer lugar.",
                    size=11, color=T.TXT_DIM, expand=True),
            ft.Container(content=ft.Icon(ft.Icons.CLOSE, color=T.TXT_FAINT, size=16),
                         ink=True, on_click=lambda e: dismiss_onboard(), padding=4, border_radius=99),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(vertical=10, horizontal=14),
        border_radius=12, bgcolor=T.WARN + "1A", border=ft.Border.all(1, T.WARN + "44"),
    )
    def dismiss_onboard():
        onboard_banner.visible = False
        c = sysint.load_config(); c["onboarded"] = True; sysint.save_config(c)
        page.update()

    # ─── botão settings (auto-start) ───
    autostart_on = {"v": sysint.is_autostart_enabled()}
    def toggle_autostart(e):
        autostart_on["v"] = not autostart_on["v"]
        ok = sysint.set_autostart(autostart_on["v"])
        settings_btn.icon_color = T.OK if (autostart_on["v"] and ok) else T.TXT_FAINT
        set_status("Abre no boot: " + ("ON" if autostart_on["v"] else "OFF"), T.OK)
        page.update()
    settings_btn = ft.IconButton(ft.Icons.ROCKET_LAUNCH, icon_size=18,
                                 icon_color=T.OK if autostart_on["v"] else T.TXT_FAINT,
                                 tooltip="Abrir junto com o Windows", on_click=toggle_autostart)

    root = ft.Container(
        opacity=0,  # fade-in na abertura
        animate_opacity=ft.Animation(400, ft.AnimationCurve.EASE_OUT),
        content=ft.Column([
            # topbar: foto + nome + bateria/status + settings
            ft.Row([
                ft.Image(src=img_path, width=52, height=52, fit=ft.BoxFit.CONTAIN),
                ft.Column([
                    ft.Text("Haylou S30 Pro", size=16, weight=ft.FontWeight.W_800, color=T.TXT),
                    ft.Row([status_dot, status_lbl], spacing=6, tight=True),
                ], spacing=2, expand=True, tight=True),
                ft.Column([
                    ft.Row([ft.Icon(ft.Icons.BATTERY_FULL, color=T.WARN, size=16), batt_text],
                           spacing=3, tight=True),
                    settings_btn,
                ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.END, tight=True),
            ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),

            onboard_banner,

            # linha AUTO (IA)
            ft.Row([auto_badge, auto_hint], spacing=10,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),

            hero,

            # chips de modo
            ft.Row([make_chip(n, m, c, i, d) for n, m, c, i, d in ANC_MODES],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

            # game mode
            ft.Container(
                content=ft.Row([
                    ft.Row([ft.Icon(ft.Icons.SPORTS_ESPORTS, color=T.TXT_DIM, size=20),
                            ft.Column([
                                ft.Text("Game Mode", size=13, color=T.TXT, weight=ft.FontWeight.W_600),
                                ft.Text("baixa latência", size=10, color=T.TXT_FAINT),
                            ], spacing=0, tight=True)], spacing=12),
                    game_switch,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=ft.Padding.symmetric(vertical=12, horizontal=16),
                border_radius=T.R_CARD, bgcolor=T.SURFACE,
            ),

            # ─── ÁUDIO DO PC (EQ + anti-leak + spatial) ───
            section("Áudio",
                ft.Column([
                    ft.Text("Equalizador", size=13, color=T.TXT, weight=ft.FontWeight.W_600),
                    ft.Text("aplica em qualquer som do PC", size=10, color=T.TXT_FAINT),
                    eq_chips_row,
                ], spacing=8, tight=True),
                ft.Row([
                    ft.Column([
                        ft.Text("Anti-vazamento", size=13, color=T.TXT, weight=ft.FontWeight.W_600),
                        ft.Text("reduz som que escapa do fone", size=10, color=T.TXT_FAINT),
                    ], spacing=0, tight=True, expand=True),
                    leak_switch,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.SURROUND_SOUND, color=T.TRANSP, size=18),
                        ft.Text("Som Espacial (Windows)", size=12, color=T.TRANSP, weight=ft.FontWeight.W_600),
                    ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
                    on_click=lambda e: wm.toggle_spatial_panel(), ink=True,
                    padding=ft.Padding.symmetric(vertical=8, horizontal=0), border_radius=10,
                    tooltip="Abre o painel de Som Espacial do Windows (Sonic/Atmos)",
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
                ], spacing=12),
                padding=16, border_radius=T.R_CARD, bgcolor=T.SURFACE,
            ),
        ], spacing=14),
        padding=ft.Padding.symmetric(vertical=20, horizontal=20),
    )

    page.add(root)
    paint_chips(1)

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
            time.sleep(5); refresh_now_playing()
    threading.Thread(target=_np_poller, daemon=True).start()

    # loop da IA de contexto (AUTO)
    paint_auto()
    threading.Thread(target=_auto_loop, daemon=True).start()

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

    # ─── NOTIFICAÇÃO de bateria baixa (avisa 1x quando cai de 20%) ───
    batt_warned = {"done": False}
    _orig_set_batt = set_batt
    def set_batt(pct):
        _orig_set_batt(pct)
        if pct <= 20 and not batt_warned["done"]:
            batt_warned["done"] = True
            sysint.notify("Haylou S30 Pro", f"Bateria baixa: {pct}%")
        elif pct > 30:
            batt_warned["done"] = False
    worker.on_batt = set_batt  # reaponta pro wrapper

    # ─── HOTKEY GLOBAL: Ctrl+Alt+A cicla ANC → Transparência → Normal ───
    def cycle_anc():
        nxt = {1: 2, 2: 0, 0: 1}.get(state["mode"], 1)
        on_anc(nxt)
    sysint.register_hotkey("ctrl+alt+a", cycle_anc)

    # ─── SYSTEM TRAY: menu rápido (clicar abre, ações trocam modo) ───
    def show_window():
        try:
            page.window.visible = True
            page.window.minimized = False
            page.window.to_front(); page.update()
        except Exception: pass
    def quit_app():
        import os as _os; _os._exit(0)
    try:
        tray["icon"] = sysint.make_tray(
            on_show=show_window,
            on_anc=lambda: on_anc(1),
            on_transp=lambda: on_anc(2),
            on_normal=lambda: on_anc(0),
            on_quit=quit_app,
            get_mode=lambda: state["mode"],
        )
    except Exception:
        pass  # tray é bônus — se falhar, app segue normal


if __name__ == "__main__":
    import sys, os
    try:
        ft.run(main)
    finally:
        sys.stderr = open(os.devnull, "w")
        os._exit(0)
