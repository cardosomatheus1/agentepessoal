"""`helpers.mcp_handler.MCPConfig` do A0 para o código que chama um conector sem o modelo (virada, fase 8): a planilha
CRM Raiz da prospecção (prospeccao/extensions/python/job_loop/_46_crm_raiz.py) chama
`MCPConfig.get_instance().call_tool("google.<ferramenta>", argumentos)`. Aqui a chamada vai ao MESMO conector que o
modelo usa (os mcp_servers do config.yaml do Hermes: o workspace-mcp no container hermes-mcp), pelo cliente MCP que já
vem no Hermes. O resultado tem o formato do A0 (`.content[].text`, `.isError`)."""
from __future__ import annotations

import sys
import types
from pathlib import Path

CONFIG = Path("/opt/data/config.yaml")


def servidores(config: Path = CONFIG) -> dict:
    import yaml

    dados = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    return {nome: str(c.get("url") or "") for nome, c in (dados.get("mcp_servers") or {}).items() if isinstance(c, dict)}


class MCPConfig:
    _instancia = None

    def __init__(self, urls: dict | None = None):
        self.urls = urls

    @classmethod
    def get_instance(cls):
        if cls._instancia is None:
            cls._instancia = cls()
        return cls._instancia

    async def call_tool(self, nome: str, argumentos: dict):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        servidor, _, ferramenta = str(nome).partition(".")
        url = (self.urls if self.urls is not None else servidores()).get(servidor)
        if not url or not ferramenta:
            raise LookupError(f"conector {servidor!r} não existe neste Hermes")
        async with streamable_http_client(url) as (leitura, escrita, *_):
            async with ClientSession(leitura, escrita) as sessao:
                await sessao.initialize()
                return await sessao.call_tool(ferramenta, argumentos or {})


def instalar() -> None:
    """sys.modules["helpers.mcp_handler"] com esta MCPConfig (os módulos mínimos da ponte_a0 antes)."""
    sys.modules["agentepessoal_ponte_a0"].instalar_modulos()
    if getattr(sys.modules.get("helpers.mcp_handler"), "MCPConfig", None) is MCPConfig:
        return
    m = types.ModuleType("helpers.mcp_handler")
    m.MCPConfig = MCPConfig
    sys.modules["helpers.mcp_handler"] = m
    sys.modules["helpers"].mcp_handler = m
