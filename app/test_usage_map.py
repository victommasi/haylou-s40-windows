"""
Testes do mapa de uso LOCAL (usage_map). Roda: python test_usage_map.py (ou pytest).
Usa um APPDATA temporário pra não tocar no config/usage real do usuário.
"""
import os
import tempfile

# precisa apontar o APPDATA pro temp ANTES de importar (usage_map lê o caminho em runtime)
os.environ["APPDATA"] = os.path.join(tempfile.gettempdir(), "haylou_usage_test")

import usage_map as um

# começa do zero
try:
    os.remove(um._path())
except OSError:
    pass

results = {"pass": 0, "fail": 0}
def check(name, got, expected):
    ok = got == expected
    results["pass" if ok else "fail"] += 1
    print(f"  {'OK' if ok else 'XX FALHOU'} {name}: got={got!r} exp={expected!r}")

print("=== period_of / period_name ===")
check("3h = madrugada(0)", um.period_of(3), 0)
check("9h = manhã(1)", um.period_of(9), 1)
check("14h = tarde(2)", um.period_of(14), 2)
check("21h = noite(3)", um.period_of(21), 3)
check("period_name 14h", um.period_name(14), "tarde")

print("=== record / predict ===")
check("sem dados -> None", um.predict("msedge", 14), None)

# 3x ANC + 1x Normal na tarde -> prevê ANC com 75%
for _ in range(3):
    um.record("msedge", 14, 1)
um.record("msedge", 14, 0)
check("ANC 75% (4 amostras)", um.predict("msedge", 14), (1, 0.75, 4))

check("outro período não herda", um.predict("msedge", 9), None)

# menos de 3 amostras -> None
um.record("discord", 20, 2)
check("1 amostra -> None", um.predict("discord", 20), None)

# sem maioria clara (2x ANC, 2x Transp = 50% < 60%) -> None
um.record("slack", 10, 1); um.record("slack", 10, 1)
um.record("slack", 10, 2); um.record("slack", 10, 2)
check("empate 50% -> None", um.predict("slack", 10), None)

check("app vazio -> None", um.predict("", 14), None)

# modo inválido não é gravado
um.record("vlc", 14, 9)
check("modo inválido ignorado", um.predict("vlc", 14), None)

print(f"\n{'='*45}")
print(f"RESULTADO: {results['pass']} passou, {results['fail']} falhou")
print('='*45)
if results["fail"]:
    raise SystemExit(1)
print('TODOS OS TESTES PASSARAM')
