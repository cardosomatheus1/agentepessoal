"""Tell the agent which connectors belong to this chat's person (others are refused)."""

import json
import sys
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

DONOS = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "donos.json"


class ConectoresPrompt(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return
        try:
            donos = json.loads(DONOS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        sep = sys.modules.get("login_usuarios_separacao")
        eu = sep.dono_contexto(self.agent.context) if sep else (self.agent.context.get_data("dono") or "matheus")
        meus = sorted(s for s, d in donos.items() if d == eu)
        outros = sorted(s for s, d in donos.items() if d != eu)
        linhas = ["## Conectores"]
        if meus:
            linhas.append(f"Conectores desta pessoa (ferramentas `<conector>.<ação>`): {', '.join(meus)}. Para e-mail, agenda e "
                          "arquivos do Google prefira o conector `google` ao navegador: é mais rápido e confiável. Eles começam "
                          "só leitura; se pedir login/autorização, abra o link no navegador e siga.")
        if outros:
            linhas.append(f"Não use nesta conversa (são de outra pessoa): {', '.join(outros)}.")
        system_prompt.append("\n".join(linhas))
