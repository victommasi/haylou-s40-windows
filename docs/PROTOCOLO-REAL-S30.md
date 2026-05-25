# Protocolo REAL do Haylou S30 Pro (capturado ao vivo via BLE no Windows)

Capturado 23/05/2026 sniffando o canal notify `cf06` enquanto apertava o botão ANC.
Este é o protocolo VERDADEIRO do S30 Pro (chipset BT828), diferente do `c010`
que estava no Java (aquele era de outro modelo Haylou).

## Canais BLE (confirmados conectando no fone)

- **Service controle:** `0000cf00-0000-1000-8000-00805f9b34fb`
- **Write (comando):** `0000cf05-...` (write / write-without-response)
- **Notify (status):** `0000cf06-...`
- Service OTA (firmware): `0000ae00` (ae01 write, ae02 notify) — não usar pra ANC

## Frame de status (recebido no cf06)

Exemplo real capturado:
```
aa bb cc c0 0e 00 0d 02 05 5a 02 08 01 02 09 00 02 0a 01 dd ee ff
```

Decomposição:
| Bytes | Significado |
|-------|-------------|
| `aa bb cc` | Header / start-of-frame |
| `c0 0e` | Opcode (report device status) |
| `00 0d` | Length do payload = 13 |
| `02 05 5a` | TLV campo **05** = 0x5a (90) → **BATERIA %** |
| `02 08 XX` | TLV campo **08** = **ANC MODE** (00/01/02) ★ |
| `02 09 00` | TLV campo **09** = 0 (?) |
| `02 0a 01` | TLV campo **0a** = 1 (config fixa, talvez "anc habilitado") |
| `dd ee ff` | Footer / end-of-frame |

### Formato TLV
Cada campo = `02 <id> <valor>` onde 02 é o tamanho (id+valor = 2 bytes).

### Campo 08 = ANC MODE (confirmado ciclando ao apertar botão)
Valores vistos: `00`, `01`, `02` (3 estados).
PENDENTE etiquetar com a orelha:
- `00` = ? (off / normal / transparência)
- `01` = ? 
- `02` = ?

## Comando de ESCRITA (cf05) — a deduzir

Hipótese: pra SETAR o ANC, mandar frame parecido no cf05. Provável formato:
```
aa bb cc [opcode-set] [len] 02 08 [modo] dd ee ff
```
Opcode de SET ainda não capturado (precisaria sniffar o app mandando, ou tentar).
O opcode `c0 0e` é REPORT (device→app). O SET (app→device) deve ser outro (ex: c0 0d, ou 0f).

## ✅ COMANDO DE ESCRITA FUNCIONANDO (24/05/2026)

O erro era usar tipo 0xC0 (= OP_READ/leitura). **Comando de escrita usa tipo 0x80.**

### Frame de comando (write no cf05) — CONFIRMADO funcionando
```
aa bb cc | 80 | F2 | len_hi len_lo | sn | [cmdData] | dd ee ff
```
- `aa bb cc` = header (RequestManager.f13610h)
- `80` = tipo COMANDO (0x80=128). LEITURA seria 0xC0=192 (OP_READ).
- `F2` = cmdId = HOP_OPCODE_SET_DEVICE_CONFIG (242)
- `len` = len(cmdData) + 1
- `sn` = opcodeSn (sequence number, usei 0x01)
- `cmdData` = configByteArray = `[payload_len+2][configId_hi][configId_lo][payload]`
- `dd ee ff` = footer (RequestManager.f13611i)

### Exemplo que FUNCIONOU
`aabbcc80f200050103000a02ddeeff` → mudou o ANC pra Transparência.
- configId = 10 (0x0a) = NOISE_REDUCTION_MODE
- payload = [0x02]

### PENDENTE: mapear os 3 valores do configId 10
`...0a 02` deu Transparência. Falta confirmar 00 e 01 (rodar e ouvir).
Provavel: 0=off, 1=anc, 2=transparencia (mas confirmar — difere do campo status 08).

### Fonte (decompilado)
- `BaseBtRequest.requestByComId()` linha 364 — monta o frame
- `EarbudCmd.OP_READ = 192` / tipo comando = 128
- `EarbudCmd.HOP_OPCODE_SET_DEVICE_CONFIG = 242`
- `RequestManager.f13610h = {aa,bb,cc}`, `f13611i = {dd,ee,ff}`
- `BtDeviceConfigRequest.getConfigByteArray()` — envelope do cmdData

## ✅ MAPA DEFINITIVO DE FEATURES (medido via run-info, 25/05/2026)

> O S30 Pro é **HEADPHONE over-ear** — NÃO é earbud TWS. Sem estojo, sem
> sensor in-ear por fone, **uma única bateria**. O SDK `com.bes.sdk` no
> decompilado (EQControl, GestureInfo, SealingInfo, MyBudsInfo, etc.) é
> genérico do chipset BES e cobre OUTROS modelos — **não reflete este hardware**.

Pedimos o run-info completo (`build_get_all`, bitmask `RUNINFO_ALL`) e lemos
cada TLV. Valor real = feature existe; `0xff` = feature ausente no hardware.

Resposta real capturada: `aabbcc000900110009020901020aff020b00020cff020f00ddeeff`

| TLV ordinal | Feature                | S30 Pro |
|-------------|------------------------|---------|
| `0x09`      | ANC mode (0/1/2)       | ✅ SUPORTADO |
| `0x0b`      | Game Mode              | ✅ SUPORTADO |
| `0x0f`      | Anti-vazamento         | ✅ SUPORTADO |
| `0x0a`      | Auto-play              | ❌ `0xff` ausente |
| `0x0c`      | **EQ preset no fone**  | ❌ `0xff` ausente |
| `0x12`–`15` | spatial/wind/wear/cena | ❌ nem reportados |

Bateria: GET_BATTERY → `aabbcc000200050002020264ddeeff` → `02 02 64` = 100% (única bateria).

**Conclusão:** o app já extrai 100% do que o protocolo HOP do S30 Pro oferece.
EQ e Áudio Espacial são entregues pelo PC (Equalizer APO + Windows Sonic),
porque o **chipset não os implementa** — confirmado pelo próprio fone, não suposto.
NÃO reinvestigar EQ-no-fone / gestos-no-fone / in-ear: o hardware respondeu `0xff`.
