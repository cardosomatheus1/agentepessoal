"""10/11: toda tela do sistema num carrossel do kit da Raiz leva o selo "Valores de exemplo" ao lado dela.
De 06 a 10/11 oito carrosséis caíram no Crítico porque a tela mostrava números sem o aviso, e moldes como o
passo-a-passo não mostram a "nota": o Designer não tinha como cumprir. Roda com o Chromium do render (na VM, o do
Hermes); sem navegador, diz que pulou."""
import json
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import render  # noqa: E402

TELAS = AQUI.parents[3] / "infra" / "vm" / "plugins" / "conteudo" / "story" / "telas"
if not TELAS.exists():  # on the VM the moldes live apart from the plugin
    TELAS = Path("/a0/usr/plugins/conteudo/story/telas")


def contar(midia: str, marca: str = "raiz") -> int:
    ficha = {"_marca": marca, "_formato": "carrossel", "objetivo": "Ler a tela da cozinha em 3 passos",
             "passos": ["Olhe o tempo de cada pedido", "Veja de onde veio o pedido", "Marque como pronto ao terminar"],
             "resultado": "Cozinha sem pedido esquecido", "midia": midia,
             "produto": {"foto": "fotos/cantina_marmita.jpg", "nome": "Raiz Connect", "detalhe": "Gestão para quem vende comida"}}
    arq = Path(tempfile.mkdtemp()) / "ficha.json"
    arq.write_text(json.dumps(ficha, ensure_ascii=False), encoding="utf-8")
    pasta, _esq, ficha, marca_d, marca_dir, formato, erros = render.carregar("passo-a-passo", arq, "carrossel")
    assert not erros, erros
    script = render.init_script(ficha, marca_d, marca_dir, formato, None)
    with render.sync_playwright() as pw:
        b, pg = render.abrir(pw, pasta, script, formato)
        n = pg.evaluate("document.querySelectorAll('.selo-exemplo').length")
        textos = pg.evaluate("[...document.querySelectorAll('.selo-exemplo')].map(e => e.textContent)")
        b.close()
    assert all(t == "Valores de exemplo" for t in textos), textos
    return n


def main() -> int:
    tela = TELAS / "cozinha-kds.jpg"
    if not tela.exists():
        print("pulado: as telas do sistema não estão nesta máquina")
        return 0
    try:
        com_tela = contar(str(tela))
    except Exception as exc:  # no browser here (CI without Chromium)
        if "Executable" in str(exc) or "executable" in str(exc) or "browser" in str(exc).lower():
            print(f"pulado: sem navegador ({type(exc).__name__})")
            return 0
        raise
    sem_tela = contar("fotos/cantina_marmita.jpg")
    falhas = 0
    for nome, cond in (("cada tela do sistema ganha o selo", com_tela >= 1),
                       ("foto comum não ganha selo", sem_tela == 0)):
        print(("ok  " if cond else "FALHOU ") + nome + f" ({com_tela}, {sem_tela})")
        falhas += not cond
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
