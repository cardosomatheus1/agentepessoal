"""Tool `concorrentes`: the watch list of competitors (the agent edits it here) and the collection that returns only
what is new since the last round (helpers/concorrentes.py)."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from helpers.tool import Response, Tool

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def _helper():
    caminho = RAIZ / "helpers" / "concorrentes.py"
    antigo, mtime = sys.modules.get("concorrentes_helper"), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location("concorrentes_helper", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules["concorrentes_helper"] = m
    return sys.modules["concorrentes_helper"]


def _fontes(valor) -> list:
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            return []
    if isinstance(valor, dict):
        valor = [valor]
    return [f for f in valor or [] if isinstance(f, dict)]


def executar(c, acao: str, kwargs: dict) -> str:
    acao = str(acao or "lista").lower()
    if acao == "lista":
        d = c.carregar()
        linhas = [f"{x['id']}: {x['nome']} — {x.get('segmento', '')}\n" + "\n".join(f"    {f['tipo']}: {f['url']}" for f in x["fontes"])
                  for x in d["concorrentes"]]
        return "\n".join(linhas) or "A lista está vazia."
    if acao == "adicionar":
        novo = c.adicionar(kwargs.get("nome", ""), kwargs.get("segmento", ""), _fontes(kwargs.get("fontes")),
                           kwargs.get("pesquisa") if isinstance(kwargs.get("pesquisa"), list) else None)
        return f"Adicionado: {novo['id']} ({len(novo['fontes'])} fonte(s)). A primeira coleta dele vira a base da comparação."
    if acao in ("fonte", "tirar_fonte"):
        c.mudar_fonte(str(kwargs.get("id") or ""), {"tipo": kwargs.get("tipo", ""), "url": kwargs.get("url", "")},
                      tirar=acao == "tirar_fonte")
        return "Fonte tirada." if acao == "tirar_fonte" else "Fonte adicionada."
    if acao == "remover":
        x = c.remover(str(kwargs.get("id") or ""), str(kwargs.get("motivo") or ""))
        return f"{x['nome']} saiu da vigia (fica guardado em 'removidos')."
    if acao == "ultima":
        r = c.ultima()
        return c.texto(r) if r else "Ainda não houve coleta."
    raise ValueError(f"acao '{acao}' não existe (lista, adicionar, fonte, tirar_fonte, remover, coletar, ultima)")


class Concorrentes(Tool):
    async def execute(self, acao: str = "lista", **kwargs) -> Response:
        c = _helper()
        try:
            if str(acao or "").lower() == "coletar":
                r = await asyncio.get_event_loop().run_in_executor(None, c.coletar)
                texto = c.texto(r)
            else:
                texto = executar(c, acao, kwargs)
        except ValueError as exc:
            texto = f"Não feito: {exc}"
        return Response(message=texto, break_loop=False)
