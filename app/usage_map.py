"""
Mapa de uso LOCAL — aprende qual modo (ANC/Transparência/Normal) você costuma
usar por app e período do dia, pra deixar o AUTO esperto sem mandar nada pra nuvem.

100% offline: grava só contagens num JSON em %APPDATA%\\haylou-win\\usage.json.
Não guarda título de janela, nem o que você ouve, nem texto — só
"app X, período Y → você escolheu o modo Z" (contador). Privado por design.
"""
import os
import json

PERIODS = ("madrugada", "manhã", "tarde", "noite")  # 0-5, 6-11, 12-17, 18-23


def _path() -> str:
    base = os.environ.get("APPDATA", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "haylou-win", "usage.json")


def _load() -> dict:
    try:
        with open(_path(), encoding="utf-8-sig") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict):
    try:
        p = _path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def period_of(hour: int) -> int:
    return 0 if hour < 6 else 1 if hour < 12 else 2 if hour < 18 else 3


def period_name(hour: int) -> str:
    return PERIODS[period_of(hour)]


def record(app: str, hour: int, mode: int):
    """Registra uma escolha MANUAL do usuário (sinal forte de preferência)."""
    if not app or mode not in (0, 1, 2):
        return
    d = _load()
    key = f"{app}|{period_of(hour)}"
    slot = d.get(key) or {}
    slot[str(mode)] = int(slot.get(str(mode), 0)) + 1
    d[key] = slot
    _save(d)


def predict(app: str, hour: int, min_samples: int = 3, min_share: float = 0.6):
    """Prevê o modo que o usuário costuma usar nesse (app, período).
    Só responde quando há histórico suficiente E uma preferência clara —
    senão retorna None (o AUTO cai na heurística de contexto).
    Retorna (modo, share 0-1, total_amostras) ou None."""
    if not app:
        return None
    slot = _load().get(f"{app}|{period_of(hour)}")
    if not slot:
        return None
    counts = {int(m): int(c) for m, c in slot.items() if m in ("0", "1", "2")}
    total = sum(counts.values())
    if total < min_samples:
        return None
    best_mode, best_count = max(counts.items(), key=lambda kv: kv[1])
    share = best_count / total
    if share < min_share:
        return None
    return (best_mode, share, total)
