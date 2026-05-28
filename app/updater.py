"""
Verificador de atualização — checa a última release no GitHub e diz se há versão
nova. Só LEITURA do endpoint público de releases (sem token, sem instalar nada
automático: só avisa e abre a página pro usuário baixar). Falha silenciosa se
offline. Sem SDK: urllib (stdlib) pra empacotar limpo no .exe.
"""
import json
import urllib.request
import urllib.error

APP_VERSION = "1.1.3"  # versão deste build (bater com a tag do release)
REPO = "revolutedigital/haylou-s30-pro-windows"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
_API = f"https://api.github.com/repos/{REPO}/releases/latest"


def _parse(v: str):
    """'v1.2.3' / '1.2.3' -> (1,2,3). Partes não-numéricas viram 0."""
    v = (v or "").strip().lstrip("vV")
    out = []
    for part in v.split(".")[:3]:
        try:
            out.append(int("".join(ch for ch in part if ch.isdigit()) or 0))
        except ValueError:
            out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def check(timeout: float = 6.0):
    """Retorna (tem_update: bool, latest_tag: str) ou (False, None) se falhar/offline.
    Compara semver simples. Nunca lança — é um 'nice to have'."""
    try:
        req = urllib.request.Request(_API, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "haylou-s30-pro-windows",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name") or ""
        if not tag:
            return (False, None)
        return (_parse(tag) > _parse(APP_VERSION), tag)
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        return (False, None)
    except Exception:
        return (False, None)
