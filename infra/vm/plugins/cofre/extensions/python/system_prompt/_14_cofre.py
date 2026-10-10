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
                  "(ex.: no campo de senha do navegador, ou no `texto` da ação `digitar` do celular) e o valor real entra só na hora de "
                  "executar — você nunca o vê. Vale para navegador, celular virtual, desktop e terminal. "
                  "Depois disso, a página e os resultados mostram `§§secret(NOME)` no lugar do valor (ele é mascarado "
                  "para você), e campos de senha costumam aparecer VAZIOS ou com pontos: isso NÃO quer dizer que falhou — o "
                  "valor real está no campo. Digite uma vez e clique em Avançar/Entrar; só conclua que falhou se o site "
                  "disser que a senha está errada. "
                  "Nunca peça senha na conversa nem a escreva em arquivos, contexto.md ou memória; se faltar uma senha, "
                  "peça para o usuário mandar no Telegram/WhatsApp `/senha NOME valor` (ex.: `/senha GMAIL_SENHA ...`; a "
                  "mensagem é apagada e você nunca vê o valor) ou usar o **Cofre de senhas** no menu do app. Para códigos "
                  "de 2FA/SMS/e-mail use `pedir_codigo`. Se o usuário mandar uma senha solta na conversa, não a use: peça "
                  "para reenviar com /senha e apagar a mensagem."]
        itens = c.lista(c.dono(self.agent.context))
        if itens:
            linhas.append("Senhas que você TEM no cofre desta pessoa (use sem perguntar):\n" + "\n".join(
                f"- {n}: {para or '(sem descrição — quando descobrir de qual conta é, registre com `cofre_descrever`)'}"
                for n, para in itens))
            linhas.append("Quando um site pedir a senha de uma conta que está nessa lista — login, \"Confirmar que é você\", "
                          "reautenticação —, use o segredo dela direto: guardar no cofre já é a autorização. Pare só para captcha "
                          "ou \"não foi possível verificar seu navegador\" (nunca contorne), para código de 2FA (use `pedir_codigo`) "
                          "e se o site disser que a senha está errada (aí avise; não tente de novo).")
        else:
            linhas.append("Nenhuma senha no cofre ainda.")
        system_prompt.append("\n".join(linhas))
