"""While the agent works on phone requests, the person sees ONE progress message that updates itself.

Two research requests by voice note ran 8–12 minutes with nothing on the phone ("tem alguma coisa errada"): a
"working on it" notice went out 90 s after a phone message with no answer yet, then a new line every 4 minutes —
per request, so 2–3 requests in parallel sent 4–8 messages (12/10 review §6). Now each person has one progress
message listing every request still running (the bridge edits it in place on Telegram; WhatsApp gets at most one
every 4 min) and, when all are answered, it turns into "✅ Terminei". The rules are in helpers/ponte.py
(proximos_andamentos), tested there.

20/10 ("às vezes fica mais de 60 min e não faço ideia do que tá acontecendo, se de fato tá executando"): its line is
now in plain words, and from 10 min on a short summary goes in a NEW message (it notifies) every 15 min, with "sem
avanço há N min" when nothing moves and "esperando …" when a slow step runs (helpers/resumo_andamento.py, tested
there). On WhatsApp, where each update of the progress message is a new message anyway, the summaries take its place.
"""

import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

from helpers.extension import Extension


def resumos():
    """helpers/resumo_andamento.py, loaded again only when the file changes (the tests put their own copy here)."""
    nome = "whatsapp_resumo_andamento"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "resumo_andamento.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def ponte():
    nome = "whatsapp_ponte"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "ponte.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        for estado in ("PENDENTES", "PEDIDOS"):
            if antigo is not None and hasattr(antigo, estado):
                setattr(modulo, estado, getattr(antigo, estado))
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _fazendo(r, pedido: dict) -> str:
    """The progress message's line, in plain words (it used to be "ajudante · passo 205 · browser · 8 min")."""
    if pedido.get("esperando"):
        return "esperando " + pedido["esperando"]
    return r.agora_codigo(pedido.get("_itens") or [])


class AndamentoCelular(Extension):
    async def execute(self, **kwargs):
        from agent import AgentContext

        p, r = ponte(), resumos()
        agora = time.time()
        contextos = list(AgentContext.all())
        aprovacoes = getattr(sys.modules.get("aprovacoes_revisor"), "PENDENTES", None) or {}  # read only
        est = r.estado()
        por_pessoa: dict[str, list] = {}  # running requests, for the progress message
        todos: dict[str, list] = {}       # every phone chat of each person, for the summaries
        for ctx in contextos:
            destino = ctx.get_data("whatsapp_de")
            entrada = ctx.get_data("whatsapp_ultima_entrada") or 0
            if not destino or not entrada:
                continue
            try:
                lido = ctx.is_running() or ctx.id in ((est.get(destino) or {}).get("pedidos") or {})
                pedido = r.montar(ctx, contextos, aprovacoes) if lido else r.basico(ctx)
            except Exception as exc:
                print(f"whatsapp: progress of {ctx.id} not read: {exc}", flush=True)
                continue
            todos.setdefault(destino, []).append(pedido)
            if pedido["rodando"]:
                por_pessoa.setdefault(destino, []).append({"pedido": pedido["pedido"], "desde": float(entrada),
                                                           "fazendo": _fazendo(r, pedido)})
        for destino, texto, fim, n in p.proximos_andamentos(por_pessoa, p.andamento_aberto(), agora, r.resumindo(est)):
            erro = await asyncio.to_thread(p.andamento, destino, texto, fim, n)
            print(f"whatsapp: progress to {destino} ({'done' if fim else f'{n} request(s)'}): {erro or 'ok'}", flush=True)
        antes = json.dumps(est, sort_keys=True)
        envios = r.planejar(todos, est, agora, r.processo())
        for envio in envios:
            try:
                texto = await asyncio.to_thread(r.texto_do_envio, envio, agora)
            except Exception as exc:
                print(f"whatsapp: summary for {envio['login']} not written: {exc}", flush=True)
                continue
            erro = await asyncio.to_thread(p.enviar_resumo, envio["login"], texto)
            print(f"whatsapp: summary ({envio['tipo']}) to {envio['login']}: {erro or 'ok'}", flush=True)
            if not erro:
                r.marcar_enviado(est, envio, agora)
        if envios or json.dumps(est, sort_keys=True) != antes:
            try:
                r.guardar(est)
            except OSError as exc:
                print(f"whatsapp: summary state not saved: {exc}", flush=True)
