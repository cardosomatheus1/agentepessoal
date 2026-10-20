"""Tell the agent which vault names exist for this person (names only, never values).

20/10 (prompt enxuto): shorter text; captcha and "never ask for a password in the chat" live in prompt_enxuto's
"Regras que valem sempre"; each entry's description is cut to DESCRICAO_MAX characters."""

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

DESCRICAO_MAX = 60  # each vault entry costs tokens in every call: keep the site and account, not a paragraph


def curto(texto) -> str:
    texto = " ".join(str(texto or "").split())
    return texto if len(texto) <= DESCRICAO_MAX else texto[: DESCRICAO_MAX - 1].rstrip() + "…"


class CofrePrompt(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return
        c = cofre()
        nomes = sorted(c.carregar(c.dono(self.agent.context)))
        linhas = ["## Cofre de senhas do usuário",
                  "Senha, token ou dado sensível: escreva `§§secret(NOME)` no argumento da ferramenta (campo de senha do "
                  "navegador, `texto` do `digitar` no celular, desktop, terminal); o valor real entra só na hora e você nunca "
                  "o vê. Depois a página mostra `§§secret(NOME)` ou o campo VAZIO/com pontos: isso NÃO é falha. Digite uma "
                  "vez e siga; só conclua que falhou se o site disser que a senha está errada (aí avise, não tente de novo). "
                  "Faltou uma senha: peça que a pessoa mande `/senha NOME valor` no Telegram/WhatsApp (a mensagem é apagada) "
                  "ou use o **Cofre de senhas** do app; senha solta na conversa não se usa: peça para reenviar com /senha."]
        itens = c.lista(c.dono(self.agent.context))
        if itens:
            linhas.append("Senhas que você TEM no cofre desta pessoa — guardar no cofre já autoriza usar no login, em "
                          "\"Confirmar que é você\" e na reautenticação, sem perguntar:\n" + "\n".join(
                f"- {n}: {curto(para) or '(sem descrição)'}" for n, para in itens))
            linhas.append("Quando a pessoa disser para que serve uma senha ou você usar uma sem descrição, registre na hora "
                          "com `cofre_descrever` (site e conta).")
        else:
            linhas.append("Nenhuma senha no cofre ainda.")
        system_prompt.append("\n".join(linhas))
