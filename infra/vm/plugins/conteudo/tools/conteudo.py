"""Tool `conteudo`: the @raiz.connect calendar, how the posts did (14/10, the weekly marketing routine of the plan)
and the week of posts proposed every Monday (20/10, helpers/semana.py). It never schedules a post by itself: the only
writes are semana.propor() (proposals, nothing scheduled), semana.aprovar() and conteudo.liberar(), both on
Matheus's explicit word. Changes to existing posts stay with the operator scripts."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from helpers.tool import Response, Tool

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def _carregar(nome: str, arquivo: str):
    caminho = RAIZ / "helpers" / arquivo
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def _helper():
    return _carregar("conteudo_helper_tool", "conteudo.py")


def _semana():
    return _carregar("conteudo_semana_tool", "semana.py")


def _dias(valor, padrao: int) -> int:
    try:
        return max(1, min(60, int(float(str(valor)))))
    except (TypeError, ValueError):
        return padrao


class Conteudo(Tool):
    async def execute(self, acao: str = "agenda", dias=7, **kwargs) -> Response:
        c = _helper()
        acao = str(acao or "agenda").lower()
        rodar = asyncio.get_event_loop().run_in_executor
        if acao == "desempenho":
            api = c.api_do_cofre()
            if not api:
                return Response(message="Sem o token da Meta no cofre (META_IG_TOKEN / META_IG_USER_ID).", break_loop=False)
            r = await rodar(None, c.desempenho, api, _dias(dias, 7))
        elif acao == "arquivos":
            r = await rodar(None, c.baixar_post, str(kwargs.get("data") or ""))
        elif acao == "propor_semana":  # the Designer and the Crítico take a while per post: off the loop
            r = await rodar(None, lambda: _semana().propor(kwargs.get("propostas"), stories=kwargs.get("stories")))
        elif acao == "aprovar_semana":
            r = await rodar(None, lambda: _semana().aprovar(str(kwargs.get("semana") or ""), kwargs.get("numeros"),
                                                             quem="matheus (pela conversa)"))
        elif acao == "semana":
            r = _semana().ver(str(kwargs.get("semana") or ""))
        elif acao == "historico":
            r = c.historico_metricas(_dias(dias, 30))
        elif acao == "antecipar_post":
            r = c.antecipar(str(kwargs.get("id") or ""), str(kwargs.get("motivo") or ""), quem="matheus (pela conversa)")
        elif acao == "liberar_post":
            r = c.liberar(str(kwargs.get("id") or ""), str(kwargs.get("motivo") or ""), quem="matheus (pela conversa)")
        else:
            r = c.agenda_proxima(_dias(dias, 7))
        return Response(message=json.dumps(r, ensure_ascii=False), break_loop=False)
