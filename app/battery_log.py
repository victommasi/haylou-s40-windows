"""
Histórico de bateria LOCAL — registra a % do fone ao longo do tempo pra mostrar
uma sparkline ("bateria nas últimas horas"). 100% offline, igual o usage_map.

Grava só pares (timestamp, pct) num JSON em %APPDATA%\\haylou-win\\battery.json.
Mantém uma janela deslizante (descarta pontos mais velhos que MAX_AGE_H horas) e
faz throttle (não grava se o último ponto foi há menos de MIN_GAP_S segundos e a
bateria não mudou) pra não inchar o arquivo.
"""
import os
import json
import time

MAX_AGE_H = 12      # mantém só as últimas 12h
MIN_GAP_S = 120     # não grava pontos a menos de 2 min de distância (salvo se mudar)
MAX_POINTS = 400    # teto duro de pontos no arquivo


def _path() -> str:
    base = os.environ.get("APPDATA", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "haylou-win", "battery.json")


def _load() -> list:
    try:
        with open(_path(), encoding="utf-8-sig") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except Exception:
        return []


def _save(points: list):
    try:
        p = _path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(points, f, ensure_ascii=False)
    except Exception:
        pass


def record(pct: int, now: float = None):
    """Registra uma leitura de bateria. Faz throttle + poda pontos velhos.
    Ignora valores fora de 0-100."""
    if not isinstance(pct, int) or not (0 <= pct <= 100):
        return
    now = now if now is not None else time.time()
    pts = _load()
    if pts:
        last_t, last_v = pts[-1]
        # throttle: pula se foi há pouco E a bateria não mudou
        if now - last_t < MIN_GAP_S and last_v == pct:
            return
    pts.append([round(now, 1), pct])
    # poda por idade e por teto de pontos
    cutoff = now - MAX_AGE_H * 3600
    pts = [pt for pt in pts if pt[0] >= cutoff][-MAX_POINTS:]
    _save(pts)


def history(now: float = None) -> list:
    """Retorna a lista [(t, pct)] dentro da janela MAX_AGE_H, mais antigo→recente."""
    now = now if now is not None else time.time()
    cutoff = now - MAX_AGE_H * 3600
    return [(t, v) for t, v in _load() if t >= cutoff]


def series(now: float = None) -> list:
    """Só os valores de bateria (pct), em ordem, pra desenhar a sparkline."""
    return [v for _t, v in history(now)]
