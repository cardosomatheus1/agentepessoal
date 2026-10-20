"""Running the tool calls of one model answer (Agent.process_llm_result_tools, replaced by
extensions/python/agent_init/_20_acoes_paralelas.py): the parallel segments of helpers/plano.py run at the same time,
the rest exactly as Agent Zero runs it (Agent._execute_tool_request, one call after the other).

A parallel segment keeps Agent Zero's steps per call: before_execution and the tool_execute_before extensions (so every
check that watches a tool still sees it, and can still stop the turn before anything runs), then the executes together
(asyncio.gather), then, in the order the model asked, tool_execute_after, the native call's output item and
after_execution (which writes the result to the history). A call that fails becomes an error result for that call
(Hermes does the same) instead of losing the results of the others; an intervention or a stop still stops the turn.

Switch: the file /a0/usr/plugins/acoes_paralelas/desligado makes every answer run as Agent Zero runs it."""

import asyncio
import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESLIGADO = Path("/a0/usr/plugins/acoes_paralelas/desligado")
_a0 = None  # the tests set a namespace with the Agent Zero names used below


def ligado() -> bool:
    try:
        return not DESLIGADO.exists()
    except OSError:
        return True


def plano():
    nome, caminho = "acoes_paralelas_plano", RAIZ / "helpers" / "plano.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def a0():
    if _a0 is not None:
        return _a0
    from types import SimpleNamespace

    from helpers.errors import HandledException, InterventionException
    from helpers.extension import call_extensions_async
    from helpers.llm_result import function_call_output_item
    from helpers.responses_tools import original_tool_name
    from helpers.tool import Response

    return SimpleNamespace(call_extensions_async=call_extensions_async, function_call_output_item=function_call_output_item,
                           original_tool_name=original_tool_name, Response=Response,
                           parar=(InterventionException, HandledException, asyncio.CancelledError))


async def processar(agent, llm_result, original):
    chamadas = list(getattr(llm_result, "function_calls", None) or [])
    if len(chamadas) < 2 or not ligado():
        return await original(agent, llm_result)
    n = a0()
    mapa = agent.get_data(type(agent).DATA_NAME_RESPONSES_TOOL_NAME_MAP)
    nomes = [n.original_tool_name(c.name, mapa) for c in chamadas]
    segmentos = plano().planejar([(nome, c.arguments) for nome, c in zip(nomes, chamadas)])
    if all(tipo == "fila" for tipo, _ in segmentos):
        return await original(agent, llm_result)
    await agent._log_response_builtin_items(llm_result)
    for tipo, idx in segmentos:
        if tipo == "fila":
            for i in idx:
                c = chamadas[i]
                r = await agent._execute_tool_request(
                    tool_name=nomes[i], tool_args=c.arguments, message=llm_result.response, raw_tool_name=nomes[i],
                    responses_item_factory=lambda resp, call=c: n.function_call_output_item(call.call_id, resp.message))
                if r:
                    return r
        else:
            r = await juntos(agent, [(chamadas[i], nomes[i]) for i in idx], llm_result.response, n)
            if r:
                return r
    return None


def _achar(agent, nome: str, args: dict, mensagem: str):
    """The tool, looked up as Agent._execute_tool_request does: MCP first, then the agent's own."""
    ferramenta = None
    try:
        import helpers.mcp_handler as mcp

        ferramenta = mcp.MCPConfig.get_instance().get_tool(agent, nome)
    except Exception:
        ferramenta = None
    return ferramenta or agent.get_tool(name=nome, method=None, args=args, message=mensagem, loop_data=agent.loop_data)


async def juntos(agent, itens, mensagem: str, n):
    preparados = []
    for chamada, nome in itens:
        args = chamada.arguments if isinstance(chamada.arguments, dict) else {}
        preparados.append((chamada, nome, args, _achar(agent, nome, args, mensagem)))
    await agent.handle_intervention()
    for chamada, nome, args, ferramenta in preparados:
        ferramenta.args = args
        await ferramenta.before_execution(**args)
        await n.call_extensions_async("tool_execute_before", agent, tool_args=args, tool_name=nome)
    agent.loop_data.current_tool = preparados[0][3]
    try:
        respostas = await asyncio.gather(*(f.execute(**a) for _c, _n, a, f in preparados), return_exceptions=True)
    finally:
        agent.loop_data.current_tool = None
    for r in respostas:
        if isinstance(r, n.parar):
            raise r
    await agent.handle_intervention()
    for (chamada, nome, args, ferramenta), r in zip(preparados, respostas):
        if isinstance(r, BaseException):
            r = n.Response(message=f"Erro ao rodar `{nome}`: {type(r).__name__}: {r}", break_loop=False)
        await n.call_extensions_async("tool_execute_after", agent, response=r, tool_name=nome)
        r.additional = {**(r.additional or {}),
                        "_responses_output_item": n.function_call_output_item(chamada.call_id, r.message)}
        await ferramenta.after_execution(r)
        if r.break_loop:
            agent._clear_responses_pending_state()
            return r.message
    return None
