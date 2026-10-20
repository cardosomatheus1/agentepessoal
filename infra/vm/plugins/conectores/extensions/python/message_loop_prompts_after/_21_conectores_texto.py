"""Text mode (the Sonnet preset, `a0_api_mode: chat`): Agent Zero sends no native tool list and writes every MCP tool
into the system prompt ("#### MCP tool `google.x`", 165 thousand characters measured on 20/10). Here that section
keeps only what the native list keeps (helpers/sob_demanda.py): the usual Google tools, GitHub's when the chat talks
about code, the ones activated with `conector`, all with the shorter description and schema; another person's
connector goes entirely. Everything else stays callable through `conector` (listar / ativar / descrever).

Runs after every system_prompt extension and before the extras (cache_prompt, _98). The Responses mode is left alone
(chat_model_call_before/_40_ferramentas_do_conector.py does it there). Any surprise leaves the prompt as it was."""

import importlib.util
import json
import sys
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("conectores_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)
DONOS = _RAIZ / "donos.json"
MARCA = "#### MCP tool `"


def donos() -> dict:
    try:
        return json.loads(DONOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def dono_da_conversa(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")


def config_mcp(agent):
    from helpers.mcp_handler import MCPConfig

    return MCPConfig.get_for_agent(agent)


class ConectoresTexto(Extension):
    async def execute(self, loop_data=None, **kwargs):
        agent = self.agent
        sistema = getattr(loop_data, "system", None)
        if agent is None or not isinstance(sistema, list) or not any(isinstance(x, str) and MARCA in x for x in sistema):
            return
        try:
            s = carregar.modulo("sob_demanda")
            if not s.ligado() or not s.modo_texto(agent):
                return
            mcp = config_mcp(agent)
            cat = s.catalogo(mcp.get_tools())
            servidores = {srv.name: srv.description for srv in getattr(mcp, "servers", []) or []}
            s.lembrar_codigo(agent)
            eu = dono_da_conversa(agent.context)
            de_outros = {servidor for servidor, dono in donos().items() if dono and dono != eu}

            def render(nome, descricao, esquema):
                return agent.read_prompt("agent.system.mcp_tool.md", qualified_name=nome, description=descricao,
                                         input_schema=esquema).strip()

            def render_servidor(nome, descricao):
                return agent.read_prompt("agent.system.mcp_server.md", server_name=nome, server_description=descricao,
                                         tools="").strip()

            ativas = set(s.ativas(agent.context))
            novo = []
            for secao in sistema:
                if isinstance(secao, str) and MARCA in secao:
                    secao = s.enxugar_mcp_texto(secao, cat, render, ativas, de_outros, render_servidor, servidores)
                    if not secao:
                        continue
                novo.append(secao)
            sistema[:] = novo
        except Exception as exc:  # never in the way of a model call
            print(f"conectores: ferramentas MCP do prompt de texto mantidas inteiras: {type(exc).__name__}: {exc}",
                  flush=True)
