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


class SegredosDaPessoa(Extension):
    async def execute(self, tool_args: dict | None = None, **kwargs):
        if not self.agent or not tool_args:
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
