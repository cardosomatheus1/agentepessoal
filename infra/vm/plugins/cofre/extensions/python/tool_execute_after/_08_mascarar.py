"""Values from the owner's vault never go back to the model: results are masked."""

import importlib.util
import sys
from pathlib import Path


def cofre():
    nome = "cofre_helper"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "cofre.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


from helpers.extension import Extension


class Mascarar(Extension):
    async def execute(self, response=None, **kwargs):
        if not self.agent or response is None or not isinstance(getattr(response, "message", None), str):
            return
        c = cofre()
        dados = c.carregar(c.dono(self.agent.context))
        if dados:
            response.message = c.mascarar(response.message, dados)
        usados = self.agent.get_data("_cofre_usados") or []
        if usados:
            self.agent.set_data("_cofre_usados", [])
            nomes = ", ".join(f"{n} ({t} caracteres)" for n, t in usados)
            response.message += (f"\n\n✅ Cofre: o valor real de {nomes} foi usado nesta ação. Campos de senha e o texto "
                                 "digitado aparecem vazios ou como §§secret(...) para você por segurança — isso é normal. "
                                 "Siga em frente (ex.: clique em Avançar/Entrar); só conclua que falhou se o site disser "
                                 "que a senha está errada.")
