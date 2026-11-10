"""10/11: na prévia do lanca-app, cada tela do tour sai duas vezes: inteira (com o menu, antes da câmera aproximar) e
no zoom do destaque. O Crítico só via o zoom e reprovava "tela cortada, sem o menu" (decisão #85) o Reel de quarta
11/11. A voz é trocada por tempos fixos (o teste não chama a Nova Sonic); sem navegador, diz que pulou."""
import json
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import render  # noqa: E402


def main() -> int:
    ficha = AQUI.parent / "lanca-app" / "exemplos" / "raiz-sistema-computador.json"
    n = len(json.loads(ficha.read_text(encoding="utf-8"))["falas"])
    render.voz = lambda f, e, m: ([round(i * 60 / (n + 1), 3) for i in range(n + 2)], None)
    saida = Path(tempfile.mkdtemp(prefix="quadro_inteiro_"))
    sys.argv = ["render.py", "lanca-app", str(ficha), "--previa", "--sem-conferir", "--saida", str(saida)]
    try:
        render.main()
    except SystemExit as e:
        if e.code not in (0, None):
            print((saida / "relatorio.json").read_text(encoding="utf-8") if (saida / "relatorio.json").exists() else e)
            return 1
    except Exception as exc:
        if "xecutable" in str(exc) or "browser" in str(exc).lower():
            print(f"pulado: sem navegador ({type(exc).__name__})")
            return 0
        raise
    rel = json.loads((saida / "relatorio.json").read_text(encoding="utf-8"))
    quadros = rel.get("quadros") or []
    inteiras = [q for q in quadros if q["tipo"] == "tela inteira"]
    zooms = [q for q in quadros if q["tipo"] == "zoom"]
    telas = len(json.loads(ficha.read_text(encoding="utf-8"))["telas"])
    falhas = 0
    for nome, cond in (("uma tela inteira por tela do tour", len(inteiras) == telas),
                       ("cada zoom tem a tela inteira da mesma cena", sorted(q["cena"] for q in zooms) == sorted(q["cena"] for q in inteiras)),
                       ("os arquivos existem e a inteira vem antes do zoom",
                        all((saida / q["arquivo"]).exists() for q in quadros)
                        and all(quadros.index(i) < quadros.index(z) for i in inteiras for z in zooms if z["cena"] == i["cena"])),
                       ("as outras cenas seguem com um quadro", any(q["tipo"] == "cena" for q in quadros))):
        print(("ok  " if cond else "FALHOU ") + nome)
        falhas += not cond
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
