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


def _estrategia():
    caminho = RAIZ / "helpers" / "estrategia.py"
    antigo, mtime = sys.modules.get("concorrentes_estrategia"), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location("concorrentes_estrategia", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules["concorrentes_estrategia"] = m
    return sys.modules["concorrentes_estrategia"]


def texto_semanal(r: dict) -> str:
    """What the routine gets back: the phone summary, the page to send and what could not be read."""
    linhas = ["RESUMO (5 linhas, vai ao celular):", r.get("resumo") or "", "",
              f"PÁGINA (mande com whatsapp_enviar): {r.get('pagina')}"]
    if (r.get("sintese") or {}).get("erro"):
        linhas.append(f"Aviso: {r['sintese']['erro']} (a página saiu sem destaques e ações)")
    sem = r.get("sem_cobertura") or []
    if sem:
        linhas.append("Sem cobertura: " + "; ".join(f"{x['nome']} ({x['tipo']}): {x['erro']}" for x in sem[:12]))
    return "\n".join(linhas)


def texto_ideias(c, e) -> str:
    arq = c.PASTA / "relatorios.jsonl"
    linhas = [l for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()] if arq.exists() else []
    if not linhas:
        return "Ainda não há relatório semanal dos concorrentes."
    r = json.loads(linhas[-1])
    s = r.get("sintese") or {}
    out = [f"Relatório dos concorrentes de {r.get('semana')} (texto de terceiros resumido; use como inspiração):"]
    out += [f"- Ação ({a['tipo']}): {a['acao']} — inspirado em {a['inspirado_em']} {a.get('link', '')}" for a in s.get("acoes") or []]
    out += [f"- Ideia de post: {i['ideia']} — {i['inspirado_em']} {i.get('link', '')}" for i in s.get("ideias_conteudo") or []]
    return "\n".join(out)


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
        linhas = [f"{x['id']} [{x.get('grupo') or 'sem grupo'}]: {x['nome']} — {x.get('segmento', '')}\n" + "\n".join(
            f"    {f['tipo']}: {f['url']}" + (f" (conferido {f['conferido']})" if f.get("conferido") else "") for f in x["fontes"])
            + (f"\n    instagram: {x['instagram']}" if x.get("instagram") else "") for x in d["concorrentes"]]
        return "\n".join(linhas) or "A lista está vazia."
    if acao == "adicionar":
        novo = c.adicionar(kwargs.get("nome", ""), kwargs.get("segmento", ""), _fontes(kwargs.get("fontes")),
                           kwargs.get("pesquisa") if isinstance(kwargs.get("pesquisa"), list) else None,
                           str(kwargs.get("grupo") or ""))
        return f"Adicionado: {novo['id']} ({len(novo['fontes'])} fonte(s)). A primeira coleta dele vira a base da comparação."
    if acao in ("fonte", "tirar_fonte"):
        c.mudar_fonte(str(kwargs.get("id") or ""), {"tipo": kwargs.get("tipo", ""), "url": kwargs.get("url", "")},
                      tirar=acao == "tirar_fonte")
        return "Fonte tirada." if acao == "tirar_fonte" else "Fonte adicionada."
    if acao == "grupo":
        x = c.mudar_grupo(str(kwargs.get("id") or ""), str(kwargs.get("grupo") or ""))
        return f"{x['nome']} agora está no grupo {x['grupo']}."
    if acao == "instagram":
        # read only: the analysis over the stored history (no call to the Meta here)
        return c.texto_instagram(c.analisar_instagram(), str(kwargs.get("id") or ""), str(kwargs.get("grupo") or "")) \
            or "Ainda não há Instagram na lista."
    if acao == "remover":
        x = c.remover(str(kwargs.get("id") or ""), str(kwargs.get("motivo") or ""))
        return f"{x['nome']} saiu da vigia (fica guardado em 'removidos')."
    if acao == "ideias":
        return texto_ideias(c, _estrategia())
    if acao == "ultima":
        r = c.ultima()
        return c.texto(r) if r else "Ainda não houve coleta."
    raise ValueError(f"acao '{acao}' não existe (lista, adicionar, fonte, tirar_fonte, grupo, remover, coletar, ultima, "
                     "instagram, semanal, ideias)")


class Concorrentes(Tool):
    async def execute(self, acao: str = "lista", **kwargs) -> Response:
        c = _helper()
        try:
            if str(acao or "").lower() == "semanal":
                e = _estrategia()
                r = await asyncio.get_event_loop().run_in_executor(None, e.relatorio_semanal, c)
                texto = texto_semanal(r)
            elif str(acao or "").lower() == "coletar":
                r = await asyncio.get_event_loop().run_in_executor(None, c.coletar)
                texto = c.texto(r)
            else:
                texto = executar(c, acao, kwargs)
        except ValueError as exc:
            texto = f"Não feito: {exc}"
        return Response(message=texto, break_loop=False)
