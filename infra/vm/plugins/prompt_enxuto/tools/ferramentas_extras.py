"""The bridge to the tools left out of the model's list (helpers/sob_demanda.py): `buscar` shows the full description
and parameters, `usar` runs the tool. The run goes through the same steps as a direct call (MCP lookup, then the
agent's own tools; the tool_execute_before/after extensions with the real tool's name, so every check that watches a
tool still sees it); the result is recorded once, as this tool's."""

import importlib.util
import sys
from pathlib import Path

from helpers.extension import call_extensions_async
from helpers.tool import Response, Tool

_RAIZ = Path(__file__).resolve().parents[1]


def _carregar():
    nome = "prompt_enxuto_carregar"
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, _RAIZ / "helpers" / "carregar.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        sys.modules[nome] = m
    return sys.modules[nome]


class FerramentasExtras(Tool):
    async def execute(self, acao: str = "", texto: str = "", nome: str = "", args=None, **kwargs) -> Response:
        c = _carregar()
        sd, en = c.modulo("sob_demanda"), c.modulo("enxuto")
        ocultas = self.agent.get_data(sd.CHAVE) or self._do_pai(sd.CHAVE) or {}
        acao = str(acao or ("usar" if nome else "buscar")).strip().lower()
        if acao == "buscar":
            nomes = sd.buscar(ocultas, texto or nome)
            if not nomes:
                return Response(message="Nenhuma ferramenta extra combina com isso. As disponíveis: "
                                        + ", ".join(sorted(ocultas)), break_loop=False)
            fichas = [sd.ficha(n, ocultas[n], en.MANUAIS.get(n, "")) for n in nomes]
            return Response(message="\n\n".join(fichas) + f"\n\nPara rodar: `{sd.PONTE}` com acao usar, nome e args.",
                            break_loop=False)
        if acao != "usar":
            return Response(message="`acao` é buscar (com `texto`) ou usar (com `nome` e `args`).", break_loop=False)

        real = sd.resolver(ocultas, nome)
        if not real:
            parecidas = sd.buscar(ocultas, nome, limite=3)
            dica = f" Parecidas: {', '.join(parecidas)}." if parecidas else ""
            return Response(message=f"A ferramenta extra `{nome}` não existe.{dica} Use acao buscar para ver as "
                                    "disponíveis.", break_loop=False)
        args = args if args is not None else {}
        if isinstance(args, str):
            import json

            try:
                args = json.loads(args or "{}")
            except ValueError as exc:
                return Response(message=f"`args` não é JSON válido ({exc}); mande um objeto.", break_loop=False)
        erro = sd.args_validos(ocultas[real], args)
        if erro:
            return Response(message=f"`{real}`: {erro}.\n\n" + sd.ficha(real, ocultas[real], en.MANUAIS.get(real, "")),
                            break_loop=False)
        return await self._rodar(real, args)

    def _do_pai(self, chave: str):
        """Inside Agent Zero's `parallel` tool the call runs in a fresh worker chat whose agent never made a model call:
        the catalog and the name map are the parent chat's (21/10: "a ferramenta extra … não existe" there)."""
        try:
            pai = self.agent.context.get_data("_parallel_parent_context_id")
            if not pai:
                return None
            from agent import AgentContext

            contexto = AgentContext.get(str(pai))
            return contexto.agent0.get_data(chave) if contexto else None
        except Exception:
            return None

    async def _rodar(self, nativo: str, args: dict) -> Response:
        from helpers.responses_tools import original_tool_name

        chave_mapa = type(self.agent).DATA_NAME_RESPONSES_TOOL_NAME_MAP
        mapa = self.agent.get_data(chave_mapa) or self._do_pai(chave_mapa) or {}
        nome = original_tool_name(nativo, mapa)
        ferramenta = None
        try:
            import helpers.mcp_handler as mcp

            ferramenta = mcp.MCPConfig.get_instance().get_tool(self.agent, nome)
        except Exception:
            ferramenta = None
        if not ferramenta:
            ferramenta = self.agent.get_tool(name=nome, method=None, args=args, message=self.message,
                                             loop_data=self.loop_data)
        if not ferramenta or type(ferramenta).__name__ == "Unknown":
            return Response(message=f"A ferramenta `{nome}` não carregou agora; tente de novo ou siga sem ela.",
                            break_loop=False)
        ferramenta.args = args
        await call_extensions_async("tool_execute_before", self.agent, tool_args=args, tool_name=nome)
        resposta = await ferramenta.execute(**args)
        await call_extensions_async("tool_execute_after", self.agent, response=resposta, tool_name=nome)
        if not isinstance(resposta, Response):
            resposta = Response(message=str(resposta or ""), break_loop=False)
        return Response(message=f"[{nome}] {resposta.message}", break_loop=resposta.break_loop,
                        additional={k: v for k, v in (resposta.additional or {}).items() if k != "_responses_output_item"}
                        or None)
