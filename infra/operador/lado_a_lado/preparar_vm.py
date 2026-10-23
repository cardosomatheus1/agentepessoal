"""Side-by-side test (23/10, Matheus: "Faça" and "Tem q garantir q tds tem msms informações q eu"): builds, inside
the agent's container, the input folder both engines get: contexto.zip (the Segundo Cérebro Pasta minus Arquivo-morto,
the AR Board criteria and the Raiz brand) plus each task's own files. Read only on live data. Run in the container:
    python3 preparar_vm.py  ->  /a0/usr/workdir/lado_a_lado/entrada/"""
import csv
import json
import shutil
import zipfile
from pathlib import Path

USR = Path("/a0/usr")
SAIDA = USR / "workdir" / "lado_a_lado" / "entrada"
PASTA = USR / "segundo_cerebro" / "pasta"


def contexto() -> Path:
    arq = SAIDA / "contexto.zip"
    with zipfile.ZipFile(arq, "w", zipfile.ZIP_DEFLATED) as z:
        for f in PASTA.rglob("*"):
            if f.is_file() and "Arquivo-morto" not in f.parts:
                z.write(f, "segundo_cerebro/" + str(f.relative_to(PASTA)))
        for f in (USR / "calibracao").glob("*/criterios.md"):
            z.write(f, f"criterios_ar_board/{f.parent.name}.md")
        marca = USR / "moldes" / "marcas" / "raiz"
        for f in marca.glob("*"):
            if f.is_file() and f.suffix in (".json", ".png", ".svg"):
                z.write(f, f"marca_raiz/{f.name}")
        z.writestr("LEIA-ME.txt", "Tudo o que o agente do Matheus sabe dele e da Raiz Connect. Comece por "
                                  "segundo_cerebro/CLAUDE.md. Decisões em segundo_cerebro/Decisoes valem até ele mudar.\n")
    return arq


def leads() -> Path:
    d = json.loads((USR / "prospeccao" / "matheus.json").read_text())
    escolhidos = [l for l in d["leads"] if l.get("etapa") in ("aquecido", "novo", "pronto") and l.get("handle")][:5]
    campos = ("handle", "nome", "segmento", "cidade", "nota", "motivo", "post_recente")
    arq = SAIDA / "leads.json"
    arq.write_text(json.dumps([{k: l.get(k) for k in campos} for l in escolhidos], ensure_ascii=False, indent=1))
    return arq


def metricas() -> Path:
    v = json.loads((USR / "painel" / "matheus.json").read_text())["fontes"]["desempenho"]["valor"]
    arq = SAIDA / "metricas_instagram_7dias.csv"
    with arq.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["data", "tipo", "link", "alcance", "salvos", "curtidas", "comentarios", "compartilhamentos", "views"])
        for p in v["posts"]:
            w.writerow([p["data"], p["tipo"], p["permalink"], p["reach"], p["saved"], p["likes"], p["comments"],
                        p["shares"], p["views"]])
    return arq


def bug() -> list:
    (SAIDA / "precos.py").write_text('''def sobra_por_venda(preco, custos):
    """Quanto sobra em reais em cada venda: preço menos a soma dos custos, com 2 casas."""
    total = 0
    for c in custos:
        total = c
    return round(preco - total, 2)


def margem(preco, custos):
    """Porcentagem que sobra do preço (0 a 100), com 1 casa."""
    return round(sobra_por_venda(preco, custos) / preco, 1)
''')
    (SAIDA / "test_precos.py").write_text('''from precos import margem, sobra_por_venda


def test_sobra():
    assert sobra_por_venda(15.0, [3.0, 2.5, 3.0]) == 6.5


def test_margem():
    assert margem(15.0, [3.0, 2.5, 3.0]) == 43.3


def test_sem_custo():
    assert sobra_por_venda(10.0, []) == 10.0
''')
    return [SAIDA / "precos.py", SAIDA / "test_precos.py"]


if __name__ == "__main__":
    if SAIDA.exists():
        shutil.rmtree(SAIDA)
    SAIDA.mkdir(parents=True)
    feitos = [contexto(), leads(), metricas(), *bug()]
    for f in feitos:
        print(f, f.stat().st_size)
