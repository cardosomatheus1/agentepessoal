"""Tool `especialista` (20/10): the main agent calls a Especialista for one task. acao=criticar asks the Crítico for a
verdict on a piece before it goes public; acao=desenhar asks the Designer for a render spec (rendered when the engine
is here), already judged by the Crítico. Matheus never talks to them directly: the agent reads the result and acts."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from helpers.tool import Response, Tool

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
PAPEL_DA_ACAO = {"criticar": "critico", "desenhar": "designer"}


def esp():
    nome, caminho = "especialistas_helper", RAIZ / "helpers" / "especialistas.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def dono(agent) -> str:
    try:
        sep = sys.modules.get("login_usuarios_separacao")
        ctx = agent.context
        return (sep.dono_contexto(ctx) if sep else (ctx.get_data("dono") or "matheus")) or "matheus"
    except Exception:
        return "matheus"


def _material(valor):
    """Text or JSON text from the agent; a JSON object stays a dict (fields of the piece, "imagens": paths)."""
    if isinstance(valor, str) and valor.strip().startswith("{"):
        try:
            return json.loads(valor)
        except ValueError:
            return valor
    return valor


def formatar_critica(c: dict) -> str:
    linhas = ["APROVADO pelo Crítico." if c.get("veredito") == "aprova"
              else "REPROVADO pelo Crítico: não publique assim; corrija e chame de novo."]
    if c.get("motivos"):
        linhas.append("Motivos:\n" + "\n".join(f"- {m}" for m in c["motivos"]))
    if c.get("sugestoes"):
        linhas.append("Sugestões:\n" + "\n".join(f"- {s}" for s in c["sugestoes"]))
    if c.get("avisos"):
        linhas.append("Julgado sem: " + "; ".join(c["avisos"]))
    return "\n".join(linhas)


def formatar_desenho(d: dict) -> str:
    linhas = ["Ficha do Designer:", json.dumps(d.get("spec") or {}, ensure_ascii=False, indent=1)]
    linhas.append("Arquivos: " + (", ".join(d["arquivos"]) if d.get("arquivos") else "nenhum renderizado"))
    if d.get("render"):
        linhas.append(f"Como renderizar: {d['render']}")
    if d.get("falta"):
        linhas.append("Falta:\n" + "\n".join(f"- {f}" for f in d["falta"]))
    linhas.append(formatar_critica(d.get("critica") or {}))
    return "\n".join(linhas)


class Especialista(Tool):
    async def execute(self, acao: str = "", papel: str = "", tipo: str = "", material=None, briefing=None,
                      **kwargs) -> Response:
        r = lambda m: Response(message=m, break_loop=False)  # noqa: E731
        acao = str(acao or "").strip().lower()
        if acao not in PAPEL_DA_ACAO:
            return r("acao desconhecida: use criticar (papel critico) ou desenhar (papel designer)")
        papel = str(papel or PAPEL_DA_ACAO[acao]).strip().lower()
        if papel != PAPEL_DA_ACAO[acao]:
            return r(f"acao {acao} é do papel {PAPEL_DA_ACAO[acao]}, não de {papel}")
        login = dono(getattr(self, "agent", None))
        m = esp()
        try:
            if acao == "criticar":
                material = _material(material if material is not None else briefing)
                if not material:
                    return r("Mande o `material`: o texto da peça (ou um JSON com os campos e `imagens`).")
                c = await asyncio.to_thread(m.criticar, str(tipo or "post"), material, login=login)
                return r(formatar_critica(c))
            briefing = _material(briefing if briefing is not None else material)
            if not briefing:
                return r("Mande o `briefing`: o que a peça precisa dizer, para quem, formato e material real disponível.")
            d = await asyncio.to_thread(m.desenhar, briefing, login=login)
            return r(formatar_desenho(d))
        except Exception as exc:
            return r(f"NÃO FEITO: o especialista falhou ({type(exc).__name__}). Não publique sem crítica.")
