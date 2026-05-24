# Protocolo BLE — Haylou S30 Pro (engenharia reversa Haylou Sound v1.5.3)

Decompilado via jadx do APK `com.yingsheng.haylousound`. Toda lógica em
`com.liesheng.module_tws.*`.

## BLE Service + Characteristics

**Service UUID:** `0000c010-0000-1000-8000-00805f9b34fb`

| Função | UUID | cmdId interno |
|--------|------|---------------|
| Clique esquerdo (1 toque) | `00000001-0000-1000-8000-00805f9b34fb` | 1 |
| Clique direito (1 toque) | `00000002-...` | 2 |
| Clique esq. duplo | `00000003-...` | 3 |
| Clique dir. duplo | `00000004-...` | 4 |
| Clique esq. triplo | `00000005-...` | 5 |
| Clique dir. triplo | `00000006-...` | 6 |
| Versão | `00000007-...` | 7 |
| **Status (lê estado)** | `00000008-...` | 8 |
| **Idioma** | `00000009-...` | 9 |
| Factory settings | `0000000a-...` | 10 |
| **EQ** | `0000000b-...` | 11 |
| Nome | `0000000c-...` | 12 |
| Low sound | `0000000d-...` | 13 |
| **ADVANCE (ANC mora aqui)** | `0000000e-...` | 14 |
| In-ear test | `00000020-...` | 32 |
| **Low latency (game mode)** | `00000021-...` | 33 |

## Envelope do pacote de config

Função `getConfigByteArray(configId, configData)` em `BtDeviceConfigRequest`:

```
byte[0]   = (configData.length + 2)        # length total - 1
byte[1]   = (configId >> 8) & 0xFF         # configId high
byte[2]   = configId & 0xFF                # configId low
byte[3..] = configData                     # payload
```

Escrito no characteristic **CHAR_ADVANCE** (`0000000e`).

## ConfigIds (CommonConfig enum)

| Config | configId | Descrição (do app, em chinês) |
|--------|----------|-------------------------------|
| HOP_CONFIG_AUDIO_FREQUENCY_MODE | 1 | 音频模式 (modo áudio) |
| HOP_CONFIG_EQ_MODE | 7 | EQ 模式 |
| HOP_CONFIG_FIND_EARBUD | 9 | achar fone |
| **HOP_CONFIG_CHANGE_NOISE_REDUCTION_MODE** | **10** | 降噪模式切换 (troca modo ANC) |
| **HOP_CONFIG_CHANGE_NOISE_REDUCTION_LEVEL** | **11** | 降噪等级选择 (nível ANC) |
| HOP_CONFIG_LISTENING_MODE | (varia) | modo de escuta |

## Comando ANC (o que importa)

### Mudar MODO de ANC (configId 10)
ANC / Transparência / Off. payload provavelmente `[modo]` onde:
- precisa confirmar valores (0=off, 1=anc, 2=transparência — a confirmar empiricamente)

Pacote: `[0x03][0x00][0x0A][modo]`  (length = 1+2 = 3)

### Mudar NÍVEL de ANC (configId 11)
Do código `getAncLevelData()`:
```java
return new byte[]{1, (byte) ancLevel.getLevel()};
```
payload = `[0x01, level]`

Pacote completo: `[0x04][0x00][0x0B][0x01][level]`  (length = 2+2 = 4)

## Leitura de estado

CHAR_STATUS (`00000008`) — notifica o estado atual (ANC, bateria, etc).
Subscrever notify pra ler.

## Pendências (confirmar empiricamente conectando no fone)

1. Valores exatos do MODO ANC (0/1/2) — testar cada um
2. Range do LEVEL (0-N) — quantos níveis o S30 Pro tem
3. Formato de leitura do CHAR_STATUS
4. EQ: formato do payload (writeEq recebe String — investigar)
