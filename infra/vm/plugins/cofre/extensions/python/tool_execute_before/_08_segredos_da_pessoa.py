"""§§secret(NAME) in a tool's arguments becomes the chat owner's value, right before it runs
(after the approval gate, which only ever sees the placeholder)."""

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


# Only tools that act on a site or system get the real value. Anything that produces text for a
# person or for storage (response, WhatsApp/Telegram, files, memory, subordinates, Sol) keeps the
# placeholder: an answer mentioning §§secret(NAME) once went out with the real password in it.
ACAO = {"browser", "code_execution_tool", "code_execution", "terminal", "code_execution_remote"}


def _age(tool_name: str) -> bool:
    nome = (tool_name or "").lower()
    return nome in ACAO or "__" in nome  # MCP tools (name__action) act on external systems


class SegredosDaPessoa(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        if not self.agent or not tool_args:
            return
        if not _age(tool_name):
            self.agent.set_data("_cofre_usados", [])
            c = cofre()

            def nome(v):  # §§secret(NAME) -> NAME: never the value (and no "unknown secret" error)
                if isinstance(v, str):
                    return c.PADRAO.sub(lambda m: m.group(1), v)
                if isinstance(v, dict):
                    return {k: nome(x) for k, x in v.items()}
                if isinstance(v, list):
                    return [nome(x) for x in v]
                return v

            for k, v in list(tool_args.items()):
                tool_args[k] = nome(v)
            return
        c = cofre()
        dados = c.carregar(c.dono(self.agent.context))
        import json

        bruto = json.dumps(tool_args, ensure_ascii=False, default=str)
        usados = sorted({n for n in c.PADRAO.findall(bruto) if n in dados})
        for k, v in list(tool_args.items()):
            tool_args[k] = c.trocar(v, dados)
        # for _08_mascarar: tell the agent plainly that the value went in (it only ever sees it masked)
        self.agent.set_data("_cofre_usados", [(n, len(dados[n])) for n in usados])
        faltando = sorted({n for n in c.PADRAO.findall(bruto) if n not in dados})
        if faltando:
            try:  # Agent Zero's own (global) secrets still apply to names it knows
                from helpers.secrets import get_secrets_manager

                globais = set(get_secrets_manager(self.agent.context).load_secrets())
            except Exception:
                globais = set()
            faltando = [n for n in faltando if n not in globais]
        if faltando:
            from helpers.errors import RepairableException

            raise RepairableException(
                f"{', '.join(faltando)} não está no cofre do usuário. Nomes disponíveis: "
                f"{', '.join(sorted(dados)) or 'nenhum'}. Use um desses ou peça para ele mandar no Telegram/WhatsApp "
                f"`/senha {faltando[0]} valor`.")
