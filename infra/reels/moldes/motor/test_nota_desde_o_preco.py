"""11/11: nos moldes de conta (conta-mudou, custo-escondido) a nota "valores de exemplo" entra junto com o primeiro
número na tela. O Crítico reprovou as prévias dos dois Reels de 15 e 18/11 porque o preço aparecia uma cena antes da
nota (R$ 22,00 e R$ 30 sem "valores de exemplo"), e a ficha não tinha como resolver."""
import re
from pathlib import Path

MOLDES = Path(__file__).resolve().parents[1]


def test_nota_entra_com_o_preco():
    conta = (MOLDES / "conta-mudou" / "molde.html").read_text(encoding="utf-8")
    linha = next(l for l in conta.splitlines() if "$('#nota').style.opacity" in l)
    assert "t >= S(1)" in linha and "S(2)" not in linha, f"conta-mudou: a nota entra na cena do preço: {linha.strip()}"
    escondido = (MOLDES / "custo-escondido" / "molde.html").read_text(encoding="utf-8")
    linha = next(l for l in escondido.splitlines() if "$('#nota').style.opacity" in l)
    assert not re.search(r"t\s*>=?\s*ini\(1\)", linha), f"custo-escondido: a nota entra no gancho, que mostra o preço: {linha.strip()}"


def test_duvida_de_dono_nao_finge_cliente():
    # 11/11: for the Raiz the question card is a common doubt, never "Pergunta de cliente comentou no post"
    molde = (MOLDES / "pergunta-cliente" / "molde.html").read_text(encoding="utf-8")
    assert "F._marca === 'raiz'" in molde and "DÚVIDA DE DONO" in molde and "de quem vende comida" in molde
    import json
    assert "duvida" in json.loads((MOLDES / "pergunta-cliente" / "esquema.json").read_text(encoding="utf-8"))["campos"]["canal"]["opcoes"]


def test_video_da_raiz_sem_nota_propria_ganha_a_do_kit():
    # 11/11: explica, mito, quiz, chat... have no "nota" field: a Raiz Reel with numbers could not say "valores de exemplo"
    js = (MOLDES / "motor" / "motor.js").read_text(encoding="utf-8")
    assert "_notaDeExemplo()" in js and js.count("Motor._notaDeExemplo();") == 1 and "nota-kit" in js
    assert ".nota-kit{" in (MOLDES / "motor" / "motor.css").read_text(encoding="utf-8")


if __name__ == "__main__":
    test_nota_entra_com_o_preco()
    test_duvida_de_dono_nao_finge_cliente()
    test_video_da_raiz_sem_nota_propria_ganha_a_do_kit()
    print("test_nota_desde_o_preco: ok")
