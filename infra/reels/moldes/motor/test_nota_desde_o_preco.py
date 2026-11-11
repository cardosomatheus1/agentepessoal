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


if __name__ == "__main__":
    test_nota_entra_com_o_preco()
    print("test_nota_desde_o_preco: ok")
