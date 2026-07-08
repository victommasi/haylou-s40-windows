"""
Motor de IA do app — Google Gemini 2.5 Flash (free tier, BYO key).

Por que Gemini Flash: tem free tier real (sem cartão), rápido, e entende PT-BR
nativamente. A chave é do usuário (BYO) porque o repo é público — nunca embutir
chave. Sem SDK: chamada REST via urllib (stdlib) pra empacotar limpo no .exe.

Duas capacidades:
  - interpret_command(text)  → ações no fone/áudio a partir de linguagem natural
  - generate_eq(description)  → bandas de EQ (dB por Hz) a partir de uma descrição

Tudo com timeout curto e erros amigáveis (sem chave, offline, rate-limit, etc).
"""
import json
import urllib.request
import urllib.error

GEMINI_MODEL = "gemini-2.5-flash"
_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
             "{model}:generateContent?key={key}")
GET_KEY_URL = "https://aistudio.google.com/app/apikey"  # chave grátis, sem cartão

# perfis de EQ que o app já tem (a IA pode escolher um deles em vez de inventar)
KNOWN_EQ = ["Padrão", "Grave +", "Vocal", "Agudo +", "Cinema", "Podcast"]


class AIError(Exception):
    """Erro amigável pra mostrar na UI."""


def has_key(api_key) -> bool:
    return bool(api_key and api_key.strip())


def _call(api_key: str, system: str, user: str, temperature: float = 0.2,
          timeout: float = 20.0) -> dict:
    """Chama o Gemini pedindo JSON puro. Retorna o dict já parseado."""
    if not has_key(api_key):
        raise AIError("Sem chave da IA. Cole sua chave grátis do Google AI Studio "
                      "nas configurações (⚙).")
    url = _ENDPOINT.format(model=GEMINI_MODEL, key=api_key.strip())
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code = e.code
        if code == 400:
            raise AIError("Chave da IA inválida. Confere a chave nas configurações.")
        if code == 429:
            raise AIError("IA atingiu o limite grátis do dia. Tenta mais tarde.")
        raise AIError(f"IA respondeu erro {code}. Tenta de novo.")
    except (urllib.error.URLError, TimeoutError):
        raise AIError("Sem internet pra falar com a IA (ela roda na nuvem do Google).")
    except Exception:
        raise AIError("Falha inesperada ao chamar a IA.")

    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, ValueError):
        # às vezes vem JSON cercado de texto — tenta extrair o bloco {...}
        try:
            i, j = text.find("{"), text.rfind("}")
            return json.loads(text[i:j + 1])
        except Exception:
            raise AIError("A IA respondeu num formato que não entendi. Tenta reformular.")


_CMD_SYSTEM = (
    "Você é o cérebro de um app de Windows que controla um fone Bluetooth Haylou S40.\n"
    "O usuário fala em português, natural. Traduza o pedido em AÇÕES e responda SÓ um JSON.\n\n"
    "Hardware do fone (controlável): modo ANC, Game Mode, Anti-vazamento.\n"
    "Áudio do PC (controlável): equalizador (via Equalizer APO) e volume do Windows.\n"
    "Extra: sleep timer (pausa a música depois de X minutos).\n\n"
    "Campos do JSON (inclua SÓ os que devem mudar; o resto deixe null):\n"
    '  anc: 0=Normal, 1=ANC (cancela ruído), 2=Transparência (ouve o ambiente) | null\n'
    "  game: true/false (modo jogo, baixa latência) | null\n"
    "  leak: true/false (anti-vazamento de som) | null\n"
    "  volume: inteiro 0-100 | null\n"
    f'  eq_profile: um de {KNOWN_EQ} se encaixar | null\n'
    "  eq_bands: lista [[Hz,ganho_dB], ...] (ganhos -8..+8) SE o usuário descrever um som "
    "que não bate com os perfis prontos | null\n"
    "  sleep_min: inteiro de minutos pro sleep timer | null\n"
    "  reply: frase curta, PT-BR, confirmando o que você fez (1 linha, sem emoji)\n\n"
    "Regras: música/foco→ANC. Call/conversa→Transparência. Jogo→game=true + ANC. "
    "Dormir→sleep_min. Se o pedido for sobre o TIMBRE do som (mais grave/agudo/quente/"
    "vocal), use eq_profile se houver match, senão eq_bands. Nunca invente campos."
)


def interpret_command(api_key: str, text: str) -> dict:
    """Linguagem natural → dict de ações. Sempre traz 'reply'."""
    out = _call(api_key, _CMD_SYSTEM, text.strip(), temperature=0.15)
    actions = {
        "anc": out.get("anc"),
        "game": out.get("game"),
        "leak": out.get("leak"),
        "volume": out.get("volume"),
        "eq_profile": out.get("eq_profile"),
        "eq_bands": out.get("eq_bands"),
        "sleep_min": out.get("sleep_min"),
        "reply": (out.get("reply") or "Feito.").strip(),
    }
    # sanidade
    if actions["anc"] not in (0, 1, 2, None):
        actions["anc"] = None
    if isinstance(actions["volume"], (int, float)):
        actions["volume"] = max(0, min(100, int(actions["volume"])))
    if actions["eq_profile"] not in KNOWN_EQ:
        actions["eq_profile"] = None
    if not isinstance(actions["sleep_min"], int) or actions["sleep_min"] <= 0:
        actions["sleep_min"] = None
    actions["eq_bands"] = _clean_bands(actions["eq_bands"])
    return actions


_EQ_SYSTEM = (
    "Você é um engenheiro de áudio. O usuário descreve em PT-BR o som que quer no fone.\n"
    "Gere uma curva de equalização e responda SÓ um JSON:\n"
    '  bands: lista de 5 a 8 pares [Hz, ganho_dB], Hz de 30 a 16000, ganho entre -8 e +8\n'
    "  summary: frase curta PT-BR explicando o ajuste (1 linha)\n"
    "Regras de bom senso: mais grave→boost 40-120Hz. Mais vocal/presença→boost 1k-4k. "
    "Mais agudo/brilho→boost 6k-12k. Som quente→leve boost grave + leve corte agudo. "
    "Evite ganhos altos demais (não passe de +8). Sempre inclua bandas que cortam também "
    "se fizer sentido, pra ficar equilibrado."
)


def generate_eq(api_key: str, description: str) -> dict:
    """Descrição → {bands:[(hz,gain)], summary}. Bands pronto pro Equalizer APO."""
    out = _call(api_key, _EQ_SYSTEM, description.strip(), temperature=0.3)
    bands = _clean_bands(out.get("bands"))
    if not bands:
        raise AIError("A IA não conseguiu gerar um EQ pra isso. Tenta descrever de outro jeito.")
    return {"bands": bands, "summary": (out.get("summary") or "EQ personalizado").strip()}


def _clean_bands(raw):
    """Valida/normaliza bandas: lista de (hz, gain) dentro de limites seguros."""
    if not isinstance(raw, list):
        return None
    out = []
    for item in raw:
        try:
            if isinstance(item, dict):
                hz, gain = item.get("hz") or item.get("Hz"), item.get("gain") or item.get("dB")
            else:
                hz, gain = item[0], item[1]
            hz = int(hz)
            gain = max(-8.0, min(8.0, float(gain)))
            if 20 <= hz <= 20000:
                out.append((hz, round(gain, 1)))
        except (TypeError, ValueError, IndexError, KeyError):
            continue
    return out or None
