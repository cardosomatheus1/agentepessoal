"""Tell the agent which connectors belong to this chat's person (others are refused)."""

import importlib.util
import json
import sys
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
DONOS = _RAIZ / "donos.json"


def _sob_demanda() -> bool:
    """helpers/sob_demanda.py is on (connector tools on demand)."""
    try:
        spec = importlib.util.spec_from_file_location("conectores_carregar", _RAIZ / "helpers" / "carregar.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.modulo("sob_demanda").ligado()
    except Exception:
        return False


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
            if any(s in meus for s in ("google", "github")) and _sob_demanda():
                linhas.append("As ferramentas comuns dos conectores (Google: Gmail buscar/ler, Agenda ler, Drive/Docs/Planilhas "
                              "ler e criar o básico; GitHub: em conversa sobre código) estão no catálogo de `ferramentas_extras`: "
                              "rode com acao \"usar\" (\"buscar\" mostra os parâmetros). Precisa de outra (editar Doc, formatar Planilha, comentários, issues…)? `conector` "
                              "acao \"listar\" e \"ativar\" (também pela `ferramentas_extras`): nada deixa de ser possível.")
        if eu == "matheus":
            linhas.append("Claude Code (linha de comando) está instalado: `claude -p \"tarefa\" --output-format json`, rodado na "
                          "pasta do projeto, usa o Claude pela AWS, sem login no site nem captcha. Use para tarefas de código que "
                          "o Matheus pedir (o IA Business está em /a0/usr/workdir/aibusiness). Para editar arquivos passe "
                          "`--permission-mode acceptEdits`; para rodar comandos, `--allowedTools \"Bash(...)\"` só com os "
                          "necessários. Tarefa longa: rode com nohup em segundo plano e acompanhe o log. Cada chamada custa "
                          "(de centavos a alguns dólares): não rode em loop.")
        if outros:
            linhas.append(f"Não use nesta conversa (são de outra pessoa): {', '.join(outros)}.")
        system_prompt.append("\n".join(linhas))
