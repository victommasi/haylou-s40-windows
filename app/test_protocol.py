"""
Suite de testes do protocolo Haylou S40.
Usa frames capturados do fone (ver docs/PROTOCOLO-REAL-S40.md).
TODO: substituir os frames de teste abaixo pelos frames reais do S40 após captura.
Roda: python -m pytest test_protocol.py -v   (ou python test_protocol.py)
"""
import haylou_protocol as p

# Frames do S30 Pro — substituir pelos frames reais do S40 após captura BLE
REPORT_ANC_BATT90 = bytes.fromhex("aabbccc00e000d0002055a020801020900020a01ddeeff")  # ANC, bat 90%
REPORT_TRANSP     = bytes.fromhex("aabbccc00e000d0002055a020800020900020a01ddeeff")  # campo08=00
GET_ANC_RESP      = bytes.fromhex("aabbcc000900050009020901ddeeff")                   # modo ANC (02 09 01)

results = {"pass": 0, "fail": 0}
def check(name, got, expected):
    ok = got == expected
    results["pass" if ok else "fail"] += 1
    mark = 'OK' if ok else 'XX FALHOU'
    print(f"  {mark} {name}: got={got!r} expected={expected!r}")

print("=== BUILD (montagem de comandos) ===")
# ANC: aabbcc 80 08 0004 01 020401 ddeeff  (confirmado funcionando no fone)
check("build_set_anc(1) ANC", p.build_set_anc(1).hex(), "aabbcc8008000401020401ddeeff")
check("build_set_anc(2) Transp", p.build_set_anc(2).hex(), "aabbcc8008000401020402ddeeff")
check("build_set_anc(0) Normal", p.build_set_anc(0).hex(), "aabbcc8008000401020400ddeeff")
check("build_set_game(True)", p.build_set_game(True).hex(), "aabbcc8008000401020501ddeeff")
check("build_set_game(False)", p.build_set_game(False).hex(), "aabbcc8008000401020500ddeeff")
check("build_get_anc (ANC+GAME)", p.build_get_anc().hex(), "aabbccc00900050900000a00ddeeff")

GET_BATT_RESP = bytes.fromhex("aabbcc000200050002020250ddeeff")  # GET_BATTERY = 80%

print("\n=== PARSE BATERIA ===")
check("GET_BATTERY (80%)", p.parse_battery(GET_BATT_RESP), 80)
check("bateria do report (90%)", p.parse_battery(REPORT_ANC_BATT90), 90)
check("bateria do transp (90%)", p.parse_battery(REPORT_TRANSP), 90)
check("bateria ausente (GET_ANC)", p.parse_battery(GET_ANC_RESP), None)
check("bateria frame vazio", p.parse_battery(b""), None)
check("build_get_battery", p.build_get_battery().hex(), "aabbccc00200050200000004ddeeff")

print("\n=== PARSE GAME MODE ===")
GAME_RESP = bytes.fromhex("aabbcc0009001100090204000206000208ff020902020b01ddeeff")
check("game mode ON (multi-attr)", p.parse_game_mode(GAME_RESP), True)
check("anc=transp no multi-attr", p.parse_anc_mode(GAME_RESP), 2)

print("\n=== PARSE MODO ANC ===")
check("modo do GET_ANC (ANC=1)", p.parse_anc_mode(GET_ANC_RESP), 1)
check("modo do report ANC (08=01)", p.parse_anc_mode(REPORT_ANC_BATT90), 1)
check("modo do report transp (08=00)", p.parse_anc_mode(REPORT_TRANSP), 0)
check("modo frame vazio", p.parse_anc_mode(b""), None)

print("\n=== VALIDACAO DE FRAME ===")
check("frame valido", p.is_valid_frame(REPORT_ANC_BATT90), True)
check("frame sem footer", p.is_valid_frame(b"\xaa\xbb\xcc\x00"), False)
check("frame vazio invalido", p.is_valid_frame(b""), False)

print("\n=== MAPEAMENTO DE NOMES ===")
check("nome modo 1", p.ANC_MODE_NAMES[1], "ANC")
check("nome->valor transparencia", p.ANC_NAME_TO_VALUE["transparencia"], 2)
check("nome->valor off", p.ANC_NAME_TO_VALUE["off"], 0)

print(f"\n{'='*45}")
print(f"RESULTADO: {results['pass']} passou, {results['fail']} falhou")
print('='*45)
if results["fail"] == 0:
    print('TODOS OS TESTES PASSARAM')
else:
    print(f'{results["fail"]} TESTE(S) FALHARAM')
    raise SystemExit(1)
