"""Ficha checks that run without a browser (CI). The render checks run in testar.py."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validar import validar  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ok = falhou = 0


def caso(nome, cond):
    global ok, falhou
    if cond: ok += 1
    else: falhou += 1; print("FALHOU:", nome)


E = {"formatos": ["reel"], "campos": {
    "titulo": {"tipo": "texto", "max": 10},
    "preco": {"tipo": "dinheiro", "real": True},
    "itens": {"tipo": "lista", "min": 2, "max": 3, "item": {"nome": {"tipo": "texto", "max": 5}, "valor": {"tipo": "dinheiro", "real": True}}},
    "quando": {"tipo": "data", "obrigatorio": False}}}
boa = {"titulo": "Oi", "preco": 10, "itens": [{"nome": "a", "valor": 1}, {"nome": "b", "valor": 2}], "_origem": {"preco": "dono", "itens": "dono"}}
caso("ficha boa passa", validar(E, boa) == [])
caso("texto longo", any("máximo é 10" in e for e in validar(E, {**boa, "titulo": "x" * 11})))
caso("travessão", any("travessão" in e for e in validar(E, {**boa, "titulo": "a — b"})))
caso("meia-risca", any("travessão" in e for e in validar(E, {**boa, "titulo": "a – b"})))
caso("emoji", any("emoji" in e for e in validar(E, {**boa, "titulo": "oi 🎂"})))
caso("dado real sem origem", any("sem origem" in e for e in validar(E, {**boa, "_origem": {}})))
caso("origem inventada não vale", any("sem origem" in e for e in validar(E, {**boa, "_origem": {"preco": "ia", "itens": "dono"}})))
caso("dado real faltando", any("dado real obrigatório" in e for e in validar(E, {k: v for k, v in boa.items() if k != "preco"})))
caso("lista curta", any("mínimo é 2" in e for e in validar(E, {**boa, "itens": boa["itens"][:1]})))
caso("item da lista validado", any("itens[1].nome" in e for e in validar(E, {**boa, "itens": [{"nome": "longo demais", "valor": 1}, boa["itens"][1]]})))
caso("data errada", any("AAAA-MM-DD" in e for e in validar(E, {**boa, "quando": "13/10/2026"})))
caso("campo desconhecido", any("não usa" in e for e in validar(E, {**boa, "extra": 1})))
caso("formato errado", any("_formato" in e for e in validar(E, {**boa, "_formato": "carrossel"})))
E2 = {"formatos": ["reel"], "campos": {"preco": {"tipo": "dinheiro", "real": True, "obrigatorio": False}}}
caso("dado real opcional ausente passa", validar(E2, {}) == [])
caso("dado real opcional presente exige origem", any("sem origem" in e for e in validar(E2, {"preco": 5})))
E3 = {"formatos": ["reel"], "campos": {"vaga": {"tipo": "objeto", "campos": {"salario": {"tipo": "dinheiro", "real": True}}}}}
caso("dado real dentro de objeto exige origem", any("sem origem" in e for e in validar(E3, {"vaga": {"salario": 2000}})))
caso("dado real dentro de objeto com origem passa", validar(E3, {"vaga": {"salario": 2000}, "_origem": {"vaga": "dono"}}) == [])
caso("número negativo em dinheiro", any("negativo" in e for e in validar(E, {**boa, "preco": -1})))

# every test ficha of every template validates; every ficha in recusadas/ is refused
for esq in sorted(RAIZ.glob("*/esquema.json")):
    e = json.loads(esq.read_text())
    for f in sorted((esq.parent / "exemplos").glob("*.json")):
        r = validar(e, json.loads(f.read_text())); caso(f"{esq.parent.name}/{f.name} passa ({r[:2]})", r == [])
    for f in sorted((esq.parent / "exemplos" / "recusadas").glob("*.json")):
        caso(f"{esq.parent.name}/recusadas/{f.name} é recusada", validar(e, json.loads(f.read_text())) != [])

print(f"validar: {ok}/{ok + falhou}")
sys.exit(1 if falhou else 0)
