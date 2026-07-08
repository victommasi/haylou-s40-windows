"""
Protocolo do Haylou S40 — funções PURAS (sem IO, testáveis).

Capturado ao vivo via RFCOMM sniffing (docs/PROTOCOLO-REAL-S40.md).
Transporte: Classic Bluetooth RFCOMM, canal 10 (NÃO é BLE/GATT).
Frame format IDÊNTICO ao S30 Pro — só o transporte mudou.

Frame de comando:  aabbcc C0 08 [len_hi len_lo] [sn] [02 attr valor] ddeeff
Frame SET_CONFIG:  aabbcc C0 F2 [len_hi len_lo] [sn] 03 [cfgId_hi cfgId_lo] [val] ddeeff
Frame SEND_EQ:     aabbcc C0 12 [len_hi len_lo] [sn] [payload ASCII EQ] ddeeff
Frame de leitura:  aabbcc C0 [op] [len] [sn] [params] ddeeff
Resposta (notify): aabbcc 00 [op] [len] [sn] [02 campo valor ...] ddeeff

Confirmados via captura 2026-07-08:
  ATTR_ANC=0x04 (0=Normal, 1=ANC, 2=Transparência, 4=modo extra)
  ATTR_MULTI=0x09 (0=OFF, 1=ON) ← CONFIRMADO
  ORD_ANC=0x09, ORD_GAME=0x0b, ORD_SPATIAL=0x12, ORD_WIND=0x14
  Bateria: opcode 02, TLV '02 02 <pct>'
  EQ hardware: SET_CONFIG configId=0x0007 (Basic Sound), opcode 0x12 (Sound Market)
"""

HEADER = bytes([0xAA, 0xBB, 0xCC])
FOOTER = bytes([0xDD, 0xEE, 0xFF])
TYPE_WRITE = 0xC0   # S40 usa C0 para comandos (S30 Pro usava 0x80)
TYPE_READ  = 0xC0   # leitura também C0
TYPE_RESP  = 0x00   # respostas do fone chegam com type=00
CMD_SET_INFO     = 0x08  # SET attrId/value — confirmado S40
CMD_GET_INFO     = 0x02  # GET device info / bateria — confirmado S40
CMD_GET_RUN_INFO = 0x09  # GET run info (bitmask) — confirmado S40
CMD_SET_CONFIG   = 0xF2  # SET_CONFIG: EQ preset por configId — confirmado S40
CMD_SEND_EQ      = 0x12  # SEND_EQ_DATA: Sound Market (payload ASCII) — confirmado S40

# ── attrIds settáveis (confirmados via captura S40) ──
ATTR_SHUTDOWN = 0x00   # timer desligar (minutos)
ATTR_EQ       = 0x02   # preset de EQ (0-9)
ATTR_SPORT    = 0x03   # modo esportivo on/off
ATTR_ANC      = 0x04   # modo ANC — CONFIRMADO: 0=Normal, 1=ANC, 2=Transparência, 4=?extra
ATTR_GAME     = 0x05   # game mode on/off
ATTR_AUTOPLAY = 0x06   # auto-play on/off
ATTR_ANTILEAK = 0x07   # anti-vazamento de som on/off
ATTR_LDAC     = 0x08   # LDAC hi-res on/off
ATTR_MULTI    = 0x09   # multipoint (2 devices) — CONFIRMADO: 0=OFF, 1=ON
ATTR_SPATIAL  = 0x0A   # áudio espacial on/off
ATTR_SPATIAL_SCENE = 0x0B  # cena do spatial
ATTR_WIND     = 0x0C   # redução de ruído de vento (toggled with multipoint in capture)
ATTR_WEAR     = 0x0D   # detecção de uso (pausa ao tirar)

ATTR_GET_ANC_STATUS = 512  # bitmask, 4 bytes big-endian

# ── EQ de hardware do S40 ── confirmado via captura 2026-07-08 ──────────────

# Basic Sound: 5 presets via SET_CONFIG (opcode F2, configId=0x0007)
CONFIG_EQ    = 0x0007
EQ_DEFAULT   = 0x00
EQ_BASS      = 0x06
EQ_ROCK      = 0x02
EQ_SOFT      = 0x07
EQ_CLASSICAL = 0x03

# lista plana: (id_str, rótulo, valor_byte) — mesma ordem exibida no app Haylou
EQ_BASIC_PRESETS = [
    ("default",   "Default",   EQ_DEFAULT),
    ("bass",      "Bass",      EQ_BASS),
    ("rock",      "Rock",      EQ_ROCK),
    ("soft",      "Soft",      EQ_SOFT),
    ("classical", "Classical", EQ_CLASSICAL),
]

# Sound Market: 3 presets via opcode 0x12 com payload ASCII (EQ paramétrico)
# Payloads capturados verbatim — bytes após [sn], antes do footer
_SM_ACOUSTIC = bytes.fromhex(
    "00db012d322c2d322c382c342c302c32302c302e382c302c322c3136302c302e372c312c"
    "2d372c3333302c302e362c312c2d362c3635302c302e362c312c2d312e352c3830302c31"
    "2e342c312c2d362c343530302c332e302c312c2d392c363730302c312e332c312c2d362c"
    "31353030302c302e380a302c302c372c342c302c32302c302e382c312c2d342e352c3230"
    "302c302e372c312c2d31302e352c3539302c302e392c312c2d352c343530302c332e302c"
    "312c2d31302c363730302c312e332c312c2d352c31353030302c302e382c312c2d322c39"
    "30302c322e30"
)
_SM_SOFT_IMM = bytes.fromhex(
    "00f2012d322c2d322c382c342c302c32302c302e382c312c2d372c3333302c302e362c31"
    "2c2d362c3635302c302e362c312c2d312e352c3830302c312e342c312c2d372c34353030"
    "2c332e302c312c2d31312c363730302c312e332c312c2d372c31353030302c302e382c31"
    "2c2d342c37302c302e380a302c302c392c342c302c32302c302e382c312c2d342e352c32"
    "30302c302e372c312c2d31302c3539302c302e392c312c2d372c343530302c322e302c31"
    "2c2d31322c363730302c312e332c312c2d362c31353030302c302e382c312c2d332c3930"
    "302c322e302c312c2d392c39302c302e382c312c2d332c33302c302e38"
)
_SM_BASS_ENH = bytes.fromhex(
    "0117012d352c2d352c31302c342c302c32302c302e382c302c352c3136302c302e372c31"
    "2c2d372c3333302c302e362c312c2d362c3635302c302e362c312c2d312e352c3830302c"
    "312e342c312c2d392c343530302c312e352c312c2d31302c363730302c312e332c312c2d"
    "392c31353030302c302e382c312c2d392c393530302c312e302c312c2d342c323030302c"
    "302e380a302c302c392c342c302c32302c302e382c312c2d342e352c3230302c302e372c"
    "312c2d31332c3539302c302e392c312c2d31302c343530302c312e352c312c2d31342c36"
    "3730302c312e332c312c2d31332c31353030302c302e382c312c2d332c3930302c322e30"
    "2c312c2d372c393030302c312e302c312c2d342e352c323030302c302e38"
)

# lista plana: (id_str, rótulo, payload_bytes)
EQ_MARKET_PRESETS = [
    ("acoustic", "Acoustic Enhanced", _SM_ACOUSTIC),
    ("soft_imm", "Soft & Immersive",  _SM_SOFT_IMM),
    ("bass_enh", "Bass Enhance",      _SM_BASS_ENH),
]

# modos ANC — confirmados via captura S40
# Valor 4 observado na captura (modo extra — pode ser ANC adaptativo ou forte)
ANC_MODE_NAMES = {0: "Normal", 1: "ANC", 2: "Transparência", 4: "ANC+"}
ANC_NAME_TO_VALUE = {"normal": 0, "off": 0, "anc": 1,
                     "transparencia": 2, "transp": 2, "ambiente": 2,
                     "anc+": 4, "adaptativo": 4}


def build_set(attr_id: int, value: int, sn: int = 1) -> bytes:
    """Comando de escrita (SET): muda ANC, multipoint, etc.
    Frame S40: aabbcc C0 08 [len] [sn] 02 [attr] [valor] ddeeff"""
    attr = bytes([0x02, attr_id, value])
    body_len = len(attr) + 1  # +1 do sn
    return (HEADER + bytes([TYPE_WRITE, CMD_SET_INFO,
            (body_len >> 8) & 0xFF, body_len & 0xFF, sn]) + attr + FOOTER)


def build_set_anc(mode: int, sn: int = 1) -> bytes:
    return build_set(ATTR_ANC, mode, sn)


def build_set_game(on: bool, sn: int = 1) -> bytes:
    return build_set(ATTR_GAME, 1 if on else 0, sn)


# ── helpers nomeados para cada feature ──
def build_set_eq(preset: int, sn: int = 1) -> bytes:      return build_set(ATTR_EQ, preset, sn)
def build_set_ldac(on: bool, sn: int = 1) -> bytes:        return build_set(ATTR_LDAC, 1 if on else 0, sn)
def build_set_spatial(on: bool, sn: int = 1) -> bytes:     return build_set(ATTR_SPATIAL, 1 if on else 0, sn)
def build_set_wear(on: bool, sn: int = 1) -> bytes:        return build_set(ATTR_WEAR, 1 if on else 0, sn)
def build_set_antileak(on: bool, sn: int = 1) -> bytes:    return build_set(ATTR_ANTILEAK, 1 if on else 0, sn)
def build_set_autoplay(on: bool, sn: int = 1) -> bytes:    return build_set(ATTR_AUTOPLAY, 1 if on else 0, sn)
def build_set_wind(on: bool, sn: int = 1) -> bytes:        return build_set(ATTR_WIND, 1 if on else 0, sn)
def build_set_sport(on: bool, sn: int = 1) -> bytes:       return build_set(ATTR_SPORT, 1 if on else 0, sn)
def build_set_multi(on: bool, sn: int = 1) -> bytes:       return build_set(ATTR_MULTI, 1 if on else 0, sn)


def build_set_config(config_id: int, value: int, sn: int = 1) -> bytes:
    """SET_CONFIG (opcode 0xF2): define parâmetro de configuração do fone.
    Frame: aabbcc C0 F2 [len] [sn] 03 [cfgId_hi] [cfgId_lo] [value] ddeeff"""
    cmd_data = bytes([3, (config_id >> 8) & 0xFF, config_id & 0xFF, value])
    body_len = len(cmd_data) + 1
    return (HEADER + bytes([TYPE_WRITE, CMD_SET_CONFIG,
            (body_len >> 8) & 0xFF, body_len & 0xFF, sn]) + cmd_data + FOOTER)


def build_set_eq_preset(preset_val: int, sn: int = 1) -> bytes:
    """Define preset de EQ Basic Sound no hardware (configId=0x0007)."""
    return build_set_config(CONFIG_EQ, preset_val, sn)


def build_send_eq_market(payload: bytes, sn: int = 1) -> bytes:
    """Envia preset Sound Market (opcode 0x12, payload ASCII EQ paramétrico).
    Frame: aabbcc C0 12 [len] [sn] [payload] ddeeff"""
    body_len = len(payload) + 1
    return (HEADER + bytes([TYPE_WRITE, CMD_SEND_EQ,
            (body_len >> 8) & 0xFF, body_len & 0xFF, sn]) + payload + FOOTER)


ATTR_BATTERY = 4  # DeviceInfoAttr.HOP_ATTR_TYPE_BATTERY — confirmado S40

def build_get_status() -> bytes:
    """GET_DEVICE_INFO (opcode 2) — info geral."""
    return HEADER + bytes([TYPE_READ, CMD_GET_INFO, 0x00, 0x00]) + FOOTER

def build_get_battery(sn: int = 0x02) -> bytes:
    """GET bateria — confirmado S40: resposta '02 02 <pct>'."""
    params = bytes([0x00, 0x00, 0x00, ATTR_BATTERY])
    body_len = len(params) + 1
    return (HEADER + bytes([TYPE_READ, CMD_GET_INFO,
            (body_len >> 8) & 0xFF, body_len & 0xFF, sn]) + params + FOOTER)


# bitmask de run info: ANC(512) + GAME_MODE(2048)
RUNINFO_ANC  = 512    # bit 9 → ORD_ANC=0x09
RUNINFO_GAME = 2048   # bit 11 → ORD_GAME=0x0b

def build_get_runinfo(bitmask: int, sn: int = 0x09) -> bytes:
    """GET_RUN_INFO (opcode 9) — pede attrs via bitmask. Resposta traz TLVs."""
    params = bytes([(bitmask >> 24) & 0xFF, (bitmask >> 16) & 0xFF,
                    (bitmask >> 8) & 0xFF, bitmask & 0xFF])
    body_len = len(params) + 1
    return (HEADER + bytes([TYPE_READ, CMD_GET_RUN_INFO,
            (body_len >> 8) & 0xFF, body_len & 0xFF, sn]) + params + FOOTER)

def build_get_anc(sn: int = 0x09) -> bytes:
    """GET ANC + GAME juntos."""
    return build_get_runinfo(RUNINFO_ANC | RUNINFO_GAME, sn)

# ── ordinais TLV do run-info (opcode 09) — confirmados via captura S40 ──
ORD_ANC     = 0x09   # CONFIRMADO: 0=Normal, 1=ANC, 2=Transp
ORD_AUTOPLAY= 0x0a
ORD_GAME    = 0x0b   # CONFIRMADO: 0=OFF
ORD_EQ      = 0x0c
ORD_MULTI   = 0x09   # multipoint lido via ATTR_MULTI (SET), estado no run-info via ORD_ANC area
ORD_LEAK    = 0x0f
ORD_SPATIAL = 0x12   # CONFIRMADO: presente (value=2)
ORD_SCENE   = 0x13   # CONFIRMADO: presente (value=0)
ORD_WIND    = 0x14   # CONFIRMADO: presente (value=0)
ORD_WEAR    = 0x15
ORD_UNK10   = 0x10   # S40: presente, value=0 — função desconhecida
ORD_UNK11   = 0x11   # S40: presente, value=0 — função desconhecida

# bitmask para pedir TODOS os estados de uma vez
# Inclui bits dos ordinais confirmados no S40
RUNINFO_ALL = (512|1024|2048|4096|32768|262144|524288|1048576|2097152|
               0x0800|0x00020000|0x00010000|0x00100000|0x00000200|0x00040000|0x00080000)

def build_get_all(sn: int = 0x09) -> bytes:
    """Pede o estado de todos os recursos de uma vez."""
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
        if v != 0xff:  # 0xff = indisponível no hardware
            return v
    return None

def parse_game_mode(frame: bytes):
    """Game mode do run info: TLV '02 0b <0|1>'. Retorna bool ou None."""
    v = parse_attr(frame, ORD_GAME)
    return bool(v) if v in (0, 1) else None


def _payload(frame: bytes) -> bytes:
    """Retorna só o miolo TLV (sem header/footer/opcode/len/sn)."""
    if len(frame) < 11:
        return b""
    return frame[8:-3]

def parse_battery(frame: bytes):
    """Extrai bateria (0-100). Retorna None se indisponível.
    S40 GET_BATTERY (opcode 02): resposta tem TLV '02 02 <pct>' confirmado = 80%.
    Report espontâneo (opcode 0e): TLV '02 05 <pct>'."""
    if len(frame) < 6:
        return None
    opcode = frame[4]
    if opcode == CMD_GET_INFO:
        i = frame.rfind(b"\x02\x02")
        if i >= 0 and i + 2 < len(frame) - 3 + 1:
            pct = frame[i + 2]
            if 0 < pct <= 100:
                return pct
        if len(frame) >= 4:
            pct = frame[-4]
            if 0 < pct <= 100:
                return pct
        return None
    # report espontâneo
    i = frame.find(b"\x02\x05")
    if i >= 0 and i + 2 < len(frame):
        pct = frame[i + 2]
        if 0 < pct <= 100:
            return pct
    return None


def parse_anc_mode(frame: bytes):
    """Extrai modo ANC. Retorna int (0/1/2/4) ou None.
    S40 GET_RUN_INFO (op 0x09): ANC em '02 09 <modo>'
    S40 REPORT espontâneo (op 0x0e): ANC provavelmente em '02 08 <modo>' (a confirmar)
    """
    if len(frame) < 6:
        return None
    opcode = frame[4]
    if opcode == 0x09:
        marker = b"\x02\x09"
    elif opcode == 0x0e:
        marker = b"\x02\x08"
    else:
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
