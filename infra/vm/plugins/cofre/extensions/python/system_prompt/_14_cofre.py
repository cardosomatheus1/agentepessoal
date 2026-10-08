"""Tell the agent which vault names exist for this person (names only, never values)."""

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


from agent import LoopData
from helpers.extension import Extension


class CofrePrompt(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return
        c = cofre()
        nomes = sorted(c.carregar(c.dono(self.agent.context)))
        linhas = ["## Cofre de senhas do usuário",
                  "Para senhas, tokens e dados sensíveis use o cofre: escreva `§§secret(NOME)` no argumento da ferramenta "
                  "(ex.: no campo de senha do navegador) e o valor real entra só na hora de executar — você nunca o vê. "
                  "Nunca peça senha na conversa nem a escreva em arquivos, contexto.md ou memória; se faltar uma senha, "
                  "peça para o usuário guardá-la no **Cofre de senhas** (menu lateral) com um nome, ou use `pedir_codigo` "
                  "para códigos de 2FA/SMS/e-mail."]
        linhas.append("Nomes disponíveis: " + (", ".join(nomes) if nomes else "(nenhum ainda)"))
        system_prompt.append("\n".join(linhas))
