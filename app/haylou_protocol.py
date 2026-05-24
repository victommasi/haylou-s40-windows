"""
Protocolo BLE do Haylou S30 Pro — funções PURAS (sem BLE, testáveis).
Reverso-engenheirado do app Haylou Sound v1.5.3 (ver docs/).

Frame de comando:  aabbcc 80 08 [len_hi len_lo] [sn] [02 attr valor] ddeeff
Frame de leitura:  aabbcc C0 [op] [len] [sn] [params] ddeeff
Resposta (notify): aabbcc [..] [..] ... [02 campo valor] ... ddeeff
"""

HEADER = bytes([0xAA, 0xBB, 0xCC])
FOOTER = bytes([0xDD, 0xEE, 0xFF])
TYPE_WRITE = 0x80
TYPE_READ = 0xC0
CMD_SET_INFO = 0x08
CMD_GET_INFO = 0x02
CMD_GET_RUN_INFO = 0x09
# ── attrIds settáveis (SetDeviceInfoAttr) — todos via frame 80 08 ──
ATTR_SHUTDOWN = 0x00   # timer desligar (minutos)
ATTR_EQ       = 0x02   # preset de EQ (0-9)
ATTR_SPORT    = 0x03   # modo esportivo on/off
ATTR_ANC      = 0x04   # modo ANC (0/1/2)
ATTR_GAME     = 0x05   # game mode on/off
ATTR_AUTOPLAY = 0x06   # auto-play on/off
ATTR_ANTILEAK = 0x07   # anti-vazamento de som on/off
ATTR_LDAC     = 0x08   # LDAC hi-res on/off
ATTR_MULTI    = 0x09   # multi-conexão (2 devices) on/off
ATTR_SPATIAL  = 0x0A   # áudio espacial on/off
ATTR_SPATIAL_SCENE = 0x0B  # cena do spatial
ATTR_WIND     = 0x0C   # redução de ruído de vento on/off
ATTR_WEAR     = 0x0D   # detecção de uso (pausa ao tirar) on/off

ATTR_GET_ANC_STATUS = 512  # bitmask, 4 bytes big-endian

# presets de EQ (DeviceEQMode) -> valor
EQ_PRESETS = [
    ("Padrão", 0), ("Vocal", 1), ("Rock", 2), ("Clássico", 3),
    ("Pop", 4), ("Grave", 5), ("Subwoofer", 6), ("Suave", 7),
    ("Outdoor", 8), ("Custom", 9),
]
EQ_NAME_TO_VAL = {n.lower(): v for n, v in EQ_PRESETS}

# modos ANC (enum AncMode do app): valor -> nome
ANC_MODE_NAMES = {0: "Normal", 1: "ANC", 2: "Transparência"}
ANC_NAME_TO_VALUE = {"normal": 0, "off": 0, "anc": 1,
                     "transparencia": 2, "transp": 2, "ambiente": 2}


def build_set(attr_id: int, value: int, sn: int = 1) -> bytes:
    """Comando de escrita (SET): muda ANC, game mode, etc."""
    attr = bytes([0x02, attr_id, value])
    body_len = len(attr) + 1  # +1 do sn
    return (HEADER + bytes([TYPE_WRITE, CMD_SET_INFO,
            (body_len >> 8) & 0xFF, body_len & 0xFF, sn]) + attr + FOOTER)


def build_set_anc(mode: int, sn: int = 1) -> bytes:
    return build_set(ATTR_ANC, mode, sn)


def build_set_game(on: bool, sn: int = 1) -> bytes:
    return build_set(ATTR_GAME, 1 if on else 0, sn)

# ── helpers nomeados pra cada recurso (todos = mesmo frame 80 08) ──
def build_set_eq(preset: int, sn: int = 1) -> bytes:      return build_set(ATTR_EQ, preset, sn)
def build_set_ldac(on: bool, sn: int = 1) -> bytes:        return build_set(ATTR_LDAC, 1 if on else 0, sn)
def build_set_spatial(on: bool, sn: int = 1) -> bytes:     return build_set(ATTR_SPATIAL, 1 if on else 0, sn)
def build_set_wear(on: bool, sn: int = 1) -> bytes:        return build_set(ATTR_WEAR, 1 if on else 0, sn)
def build_set_antileak(on: bool, sn: int = 1) -> bytes:    return build_set(ATTR_ANTILEAK, 1 if on else 0, sn)
def build_set_autoplay(on: bool, sn: int = 1) -> bytes:    return build_set(ATTR_AUTOPLAY, 1 if on else 0, sn)
def build_set_wind(on: bool, sn: int = 1) -> bytes:        return build_set(ATTR_WIND, 1 if on else 0, sn)
def build_set_sport(on: bool, sn: int = 1) -> bytes:       return build_set(ATTR_SPORT, 1 if on else 0, sn)
def build_set_multi(on: bool, sn: int = 1) -> bytes:       return build_set(ATTR_MULTI, 1 if on else 0, sn)


ATTR_BATTERY = 4  # DeviceInfoAttr.HOP_ATTR_TYPE_BATTERY

def build_get_status() -> bytes:
    """GET_DEVICE_INFO (opcode 2) — info geral."""
    return HEADER + bytes([TYPE_READ, CMD_GET_INFO, 0x00, 0x00]) + FOOTER

def build_get_battery(sn: int = 0x02) -> bytes:
    """GET bateria: opcode 2 + attrId 4 (big-endian). Resposta confiável '02 02 <pct>'."""
    params = bytes([0x00, 0x00, 0x00, ATTR_BATTERY])
    body_len = len(params) + 1
    return (HEADER + bytes([TYPE_READ, CMD_GET_INFO,
            (body_len >> 8) & 0xFF, body_len & 0xFF, sn]) + params + FOOTER)


# bitmask de run info: ANC(512) + GAME_MODE(2048) — lidos juntos no startup
RUNINFO_ANC = 512
RUNINFO_GAME = 2048

def build_get_runinfo(bitmask: int, sn: int = 0x09) -> bytes:
    """GET_RUN_INFO (opcode 9) — pede attrs via bitmask. Resposta traz TLVs."""
    params = bytes([(bitmask >> 24) & 0xFF, (bitmask >> 16) & 0xFF,
                    (bitmask >> 8) & 0xFF, bitmask & 0xFF])
    body_len = len(params) + 1
    return (HEADER + bytes([TYPE_READ, CMD_GET_RUN_INFO,
            (body_len >> 8) & 0xFF, body_len & 0xFF, sn]) + params + FOOTER)

def build_get_anc(sn: int = 0x09) -> bytes:
    """GET_ANC + GAME juntos (lê os dois estados de uma vez)."""
    return build_get_runinfo(RUNINFO_ANC | RUNINFO_GAME, sn)

# ── ordinais dos attrs no TLV de resposta do run info (opcode 09) ──
ORD_ANC=0x09; ORD_AUTOPLAY=0x0a; ORD_GAME=0x0b; ORD_EQ=0x0c
ORD_LEAK=0x0f; ORD_SPATIAL=0x12; ORD_SCENE=0x13; ORD_WIND=0x14; ORD_WEAR=0x15

# bitmask pra pedir TODOS os estados de uma vez
RUNINFO_ALL = (512|1024|2048|4096|32768|262144|524288|1048576|2097152)

def build_get_all(sn: int = 0x09) -> bytes:
    """Pede o estado de todos os recursos de uma vez (run info bitmask)."""
    return build_get_runinfo(RUNINFO_ALL, sn)

def parse_attr(frame: bytes, ordinal: int):
    """Lê valor de um attr no TLV '02 <ordinal> <valor>' do run info (opcode 09).
    Retorna int (0-255) ou None."""
    if len(frame) < 6 or frame[4] != 0x09:
        return None
    marker = bytes([0x02, ordinal])
    k = frame.find(marker)
    if k >= 0 and k + 2 < len(frame):
        v = frame[k + 2]
        if v != 0xff:  # 0xff = indisponível
            return v
    return None

def parse_game_mode(frame: bytes):
    """Game mode do run info: TLV '02 0b <0|1>'. Retorna bool ou None."""
    v = parse_attr(frame, ORD_GAME)
    return bool(v) if v in (0, 1) else None


def _payload(frame: bytes) -> bytes:
    """Retorna só o miolo TLV: tira header(3)+type+opcode+len(2)+sn(1) e footer(3).
    Estrutura resposta: aabbcc <type> <op> <len_hi len_lo> <sn> [TLVs...] ddeeff"""
    if len(frame) < 11:
        return b""
    return frame[8:-3]  # pula 8 bytes de cabeçalho, 3 de footer

def parse_battery(frame: bytes):
    """Extrai bateria (0-100). Retorna None se indisponível.
    - GET_BATTERY (opcode 2): resposta termina com '02 02 <pct> ddeeff' → pct é o byte antes do footer.
    - Report espontâneo (opcode 0e): TLV '02 05 <pct>'."""
    if len(frame) < 6:
        return None
    opcode = frame[4]
    if opcode == CMD_GET_INFO:
        # resposta do GET_BATTERY: attrId 02 seguido do valor, logo antes do footer ddeeff
        i = frame.rfind(b"\x02\x02")  # ultimo '02 02' (attrId bateria)
        if i >= 0 and i + 2 < len(frame) - 3 + 1:
            pct = frame[i + 2]
            if 0 < pct <= 100:
                return pct
        # fallback: byte antes do footer
        if len(frame) >= 4:
            pct = frame[-4]
            if 0 < pct <= 100:
                return pct
        return None
    # report espontaneo
    i = frame.find(b"\x02\x05")
    if i >= 0 and i + 2 < len(frame):
        pct = frame[i + 2]
        if 0 < pct <= 100:
            return pct
    return None


def parse_anc_mode(frame: bytes):
    """Extrai modo ANC de um frame. Retorna None se não achar.

    Distingue pelo OPCODE do frame (byte 4), porque os campos TLV têm
    significado diferente por tipo de resposta:
      - GET_RUN_INFO (op 0x09): ANC está em '02 09 <modo>'
      - REPORT espontâneo (op 0x0e): ANC está em '02 08 <modo>'
        (cuidado: report tb tem '02 09 00' que NÃO é ANC)
    """
    if len(frame) < 6:
        return None
    opcode = frame[4]  # aa bb cc <type> <opcode>
    if opcode == 0x09:        # GET_RUN_INFO resp -> ANC em 02 09
        marker = b"\x02\x09"
    elif opcode == 0x0e:      # REPORT espontâneo -> ANC em 02 08
        marker = b"\x02\x08"
    else:
        # desconhecido: tenta 08 primeiro (report é o mais comum)
        for m in (b"\x02\x08", b"\x02\x09"):
            k = frame.find(m)
            if k >= 0 and k + 2 < len(frame) and frame[k + 2] in ANC_MODE_NAMES:
                return frame[k + 2]
        return None
    k = frame.find(marker)
    if k >= 0 and k + 2 < len(frame):
        modo = frame[k + 2]
        if modo in ANC_MODE_NAMES:
            return modo
    return None


def is_valid_frame(frame: bytes) -> bool:
    """Frame válido começa com header e termina com footer."""
    return len(frame) >= 6 and frame[:3] == HEADER and frame[-3:] == FOOTER
