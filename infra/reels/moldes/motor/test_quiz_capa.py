"""12/11: o carrossel de quiz de 24/11 da Raiz saiu com a capa quase vazia: duas linhas no topo ("Valores de exemplo:
aluguel R$ 1.800, queijo R$ 600. Qual conta vence sem pedidos?") e 70% da arte sem nada. No carrossel a capa (a
pista) pede foto em "midia" e os números vão em "conta", o cartão que o código soma, com a "nota" junto. Roda com o
Chromium do render (na VM, o do Hermes); sem navegador, diz que pulou."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent

BASE = {"_marca": "raiz", "_formato": "carrossel", "pergunta": "Quanto custa cada coxinha boa?",
        "opcoes": ["R$ 2,00", "R$ 2,31", "R$ 2,60"], "certa": "B",
        "explicacao": "A receita custa o mesmo, mas só as boas vendem: divida pelo que sai, não pelo que a receita promete.",
        "assunto": "negocio",
        "produto": {"foto": "fotos/raiz_calculadora.jpg", "nome": "Lucro na Mão em 30 Dias",
                    "detalhe": "Veja quanto sobra em cada produto", "convite": "toque no link da bio"}}


def render(ficha: dict) -> tuple[int, str, Path]:
    pasta = Path(tempfile.mkdtemp())
    arq = pasta / "ficha.json"
    arq.write_text(json.dumps(ficha, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(AQUI / "render.py"), "quiz", str(arq), "--formato", "carrossel",
                        "--saida", str(pasta / "saida")], capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr, pasta / "saida"


def main() -> int:
    casos = []
    # 12/11: Chromium on the Hermes's scratch TMPDIR hung (a 15-minute render) or crashed the page
    casos.append(("o navegador do render usa TMPDIR em /tmp", '"TMPDIR": "/tmp"' in (AQUI / "render.py").read_text(encoding="utf-8")))
    cod, saida, _ = render(dict(BASE, pista="Valores de exemplo: aluguel R$ 1.800, queijo R$ 600. Qual conta vence?"))
    if "Executable" in saida or "executable" in saida or "playwright" in saida.lower() and cod not in (0, 2, 3):
        print("pulado: sem navegador")
        return 0
    casos.append(("R$ no texto da pista é recusado", cod == 2 and 'pista: sem "R$"' in saida))
    casos.append(("capa do carrossel sem foto é recusada", cod == 2 and 'precisa de foto em "midia"' in saida))
    boa = dict(BASE, pista="Uma coxinha leva massa, recheio, óleo, gás e embalagem.", midia="fotos/cantina_coxinhas.jpg",
               conta=[{"rotulo": "Massa e recheio", "valor": 1.6}, {"rotulo": "Óleo e gás", "valor": 0.4},
                      {"rotulo": "Embalagem", "valor": 0.31}], nota="valores de exemplo", _origem={"conta": "dono"})
    cod, saida, pasta = render(boa)
    casos.append(("capa com foto, conta e nota sai", cod == 0 and (pasta / "slide1.jpg").exists()))
    falhas = 0
    for nome, cond in casos:
        print(("ok  " if cond else "FALHOU ") + nome)
        falhas += not cond
    if falhas:
        print(saida[-1500:])
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
