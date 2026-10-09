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
                          "arquivos do Google prefira o conector `google` ao navegador: é mais rápido e confiável. Se pedir "
                          "login/autorização, mande o link ao usuário pelo celular para ele autorizar.")
            if "google" in meus:
                linhas.append("Google: Gmail e Agenda são só leitura. Drive, Docs e Planilhas você pode criar e editar: quando a "
                              "entrega for tabela/comparação use uma Planilha, texto/relatório use um Doc (além de PDF se pedirem), "
                              "sempre dentro da pasta \"Agente\" do Drive (crie se não existir) e mande o link. Edite só arquivos "
                              "que você criou ou que o usuário indicou; não compartilhe com ninguém nem apague arquivos.")
        if outros:
            linhas.append(f"Não use nesta conversa (são de outra pessoa): {', '.join(outros)}.")
        system_prompt.append("\n".join(linhas))
