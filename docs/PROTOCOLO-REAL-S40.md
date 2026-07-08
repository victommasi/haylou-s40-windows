# Protocolo Real do Haylou S40 — Documentação Completa

**Capturado via HCI snoop log — 2026-07-08**  
**Método:** Android bug report (Motorola Edge 70) + Wireshark  
**Status:** CONFIRMADO ✅

---

## 1. Transporte

| Campo | Valor |
|---|---|
| Protocolo | **Classic Bluetooth (BR/EDR) — NÃO é BLE** |
| Layer | RFCOMM sobre L2CAP (PSM=0x0003) |
| Canal RFCOMM | **10** (DLCI=0x14) |
| MAC do S40 | `24:B2:31:xx:xx:xx` (OUI confirmado) |
| Nome Bluetooth | `HAYLOU S40` |

> **Importante:** o S40 também usa HFP (canal 4) para chamadas e A2DP/AVDTP para
> áudio. O canal **10** é o canal proprietário de controle (ANC, Multipoint, etc.).

---

## 2. Formato do Frame

Idêntico ao S30 Pro:

```
AA BB CC  [TYPE]  [OPCODE]  [LEN_HI LEN_LO]  [SN]  [PAYLOAD...]  DD EE FF
```

| Campo | Tamanho | Notas |
|---|---|---|
| Header | 3 bytes | `AA BB CC` fixo |
| TYPE | 1 byte | `C0` = comando/leitura do app; `00` = resposta do fone |
| OPCODE | 1 byte | ver tabela abaixo |
| LEN | 2 bytes | big-endian, inclui o byte SN |
| SN | 1 byte | sequence number (incrementa a cada comando) |
| PAYLOAD | LEN-1 bytes | TLVs ou parâmetros |
| Footer | 3 bytes | `DD EE FF` fixo |

---

## 3. Opcodes Confirmados

| Opcode | Direção | Descrição |
|---|---|---|
| `0x02` | App→S40 | GET_DEVICE_INFO (bateria, nome) |
| `0x08` | App→S40 | SET_ATTR — seta um atributo |
| `0x09` | App→S40 | GET_RUN_INFO — lê estado via bitmask |
| `0xF2` | App→S40 | SET_CONFIG — configura parâmetro interno |
| `0xF3` | App→S40 | GET_CONFIG |
| `0x00` | S40→App | Resposta genérica (ACK) |

---

## 4. Exemplos de Frames Capturados

### 4.1 GET_BATTERY (App→S40)
```
AA BB CC  C0 02 00 05 02  00 00 00 04  DD EE FF
           ↑ op  ↑ sn    ↑ attrId=4 (battery)
```

### 4.2 GET_BATTERY Response (S40→App) — bateria = 80%
```
AA BB CC  00 02 00 05 00  00 02 02 50  DD EE FF
                              ↑↑  ↑ TLV: attr=0x02, val=0x50=80%
```

### 4.3 SET_ANC — Normal (0)
```
AA BB CC  C0 08 00 04 0B  02 04 00  DD EE FF
           ↑ op  ↑ sn    ↑ TLV: attr=0x04 (ANC), val=0x00 (Normal)
```

### 4.4 SET_ANC — ANC on (1)
```
AA BB CC  C0 08 00 04 0D  02 04 01  DD EE FF
```

### 4.5 SET_ANC — Transparência (2)
```
AA BB CC  C0 08 00 04 0C  02 04 02  DD EE FF
```

### 4.6 SET_ANC — Modo extra ANC+ (4)
```
AA BB CC  C0 08 00 04 0A  02 04 04  DD EE FF
```

### 4.7 SET_MULTIPOINT ON (CONFIRMADO)
```
AA BB CC  C0 08 00 04 10  02 09 01  DD EE FF
                          ↑ TLV: attr=0x09 (Multipoint), val=0x01 (ON)
```

### 4.8 SET_MULTIPOINT OFF (CONFIRMADO)
```
AA BB CC  C0 08 00 04 12  02 09 00  DD EE FF
```

### 4.9 GET_RUN_INFO Response — ANC mode (ordinal 0x09)
```
AA BB CC  00 09 00 05 00  06 02 09 01  DD EE FF
                          ↑ req_sn  ↑ TLV: ord=0x09 (ANC), val=0x01 (ANC on)
```

---

## 5. Atributos SET (opcode 0x08)

TLV format: `02 <attrId> <value>`

| attrId | Feature | Valores confirmados |
|---|---|---|
| `0x04` | **ANC Mode** ✅ | 0=Normal, 1=ANC, 2=Transparência, 4=ANC+ |
| `0x09` | **Multipoint** ✅ | 0=OFF, 1=ON |
| `0x0C` | Wind/Feature extra | 0=OFF, 1=ON (toggled com multipoint na captura) |
| `0x05` | Game Mode | 0=OFF, 1=ON (herdado S30 Pro — a confirmar) |
| `0x07` | Anti-leak | 0=OFF, 1=ON (herdado S30 Pro — a confirmar) |

---

## 6. Ordinais Run-Info (opcode 0x09)

TLV na resposta: `02 <ordinal> <value>`

| Ordinal | Feature | Valor capturado |
|---|---|---|
| `0x09` | **ANC Mode** ✅ | 1 (ANC ativo) |
| `0x0B` | **Game Mode** ✅ | 0 (OFF) |
| `0x0E` | Anti-leak? | — |
| `0x10` | Desconhecido | 0 |
| `0x11` | Desconhecido | 0 |
| `0x12` | Spatial audio | 2 |
| `0x13` | Spatial scene | 0 |
| `0x14` | Wind reduction | 0 |

---

## 7. Informações do Dispositivo (GET_DEVICE_INFO response)

```
AA BB CC  00 02 00 1F 00  01 0B 00 48 41 59 4C 4F 55 20 53 34 30 ...  DD EE FF
                           ↑ TLV nome: "HAYLOU S40" (11 bytes ASCII)
```

Inclui: nome (01), firmware (07), bateria (02 02 50 = 80%), e outros TLVs.

---

## 8. Conexão no Windows (Python)

```python
import socket

AF_BTH        = 32  # Windows-specific
BTHPROTO_RFCOMM = 3
CTRL_CHANNEL  = 10  # canal proprietário do S40

s = socket.socket(AF_BTH, socket.SOCK_STREAM, BTHPROTO_RFCOMM)
s.connect(("24:B2:31:XX:XX:XX", CTRL_CHANNEL))  # MAC do seu S40
s.sendall(frame_bytes)
response = s.recv(512)
```

Discovery (1ª conexão, sem endereço salvo): usar `winsdk.windows.devices.enumeration.DeviceInformation`
com selector de Bluetooth AEP, filtrar por nome "HAYLOU S40" ou OUI `24:B2:31`.

---

## 9. Outros Protocolos Observados no Mesmo Dispositivo

| PSM L2CAP | Protocolo | Uso |
|---|---|---|
| 0x0001 | SDP | Descoberta de serviços (setup) |
| 0x0003 | RFCOMM | **Controle proprietário (canal 10)** |
| 0x0017 | AVDTP | Streaming de áudio (A2DP) |
| 0x0019 | AVCTP | Controles de mídia (AVRCP) |
| HFP canal 4 | HFP | Chamadas telefônicas |
