"""Tool `cerebro` (20/10): the agent's hands on the Segundo Cérebro's Pasta, besides `decisao` and `fios`: search it,
record or move an Assunto, log a meeting he tells about (Reunioes/, linked to its Decisões and Pendências), undo what
the automatic anotação got wrong, run the context interview (one section at a time, written only after his ok), write
the nota do dia now, run the audit."""

import asyncio
import importlib.util
import json
import re
import sys
import uuid
from pathlib import Path

from helpers.tool import Response, Tool

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def mods():
    nome, caminho = "cerebro_modulos", RAIZ / "helpers" / "modulos.py"
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]


def dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")) or "matheus"


def desfazer(m, ref: str, motivo: str, login: str = "matheus") -> list:
    """Undo items ('decisao:35', 'pendencia:ab12cd', 'assunto:x1y2z3' or 'ultimo': the last anotação)."""
    p, cap = m.m("pasta"), m.m("captura")
    refs = cap.ler_estado(p.RAIZ).get("ultimo", []) if str(ref).strip() == "ultimo" else [str(ref).strip()]
    feito = []
    for r in refs:
        tipo, _, ident = r.partition(":")
        if tipo == "decisao" and m.m("decisoes").revogar(login, ident, motivo=motivo or "desfeito a pedido dele",
                                                          por="agente: desfazer"):
            feito.append(r)
        elif tipo == "pendencia" and m.m("fios").obter(login, ident):
            m.m("fios").mesclar(login, [{"id": ident, "estado": "ignorado", "motivo": motivo or "desfeito a pedido dele"}])
            feito.append(r)
        elif tipo == "assunto" and m.m("assuntos").desfazer(ident):
            feito.append(r)
    if feito:
        p.versionar(f"desfeito: {', '.join(feito)}")
    return feito


_REF = re.compile(r"^(decisao|pendencia):\S+$")


def _achar_ref(p, item: str, candidatos: list[dict], tipo: str, campo: str) -> str:
    """'decisao:N'/'pendencia:id' as given; else the one open item whose title has every word of the text; else ''."""
    if _REF.match(item):
        return item
    palavras = [w for w in p.slug(item, 200).split("-") if len(w) > 2]
    achados = [c for c in candidatos if palavras and all(w in p.slug(c.get(campo) or "", 400) for w in palavras)]
    return f"{tipo}:{achados[0]['id']}" if len(achados) == 1 else ""


def reuniao(m, login: str, titulo: str, data: str = "", participantes="", resumo: str = "", decisoes=None,
            proximos=None, area: str = "") -> dict:
    """A meeting he told about: decisions as links when registered (or their text), next steps linked to the
    Pendências they are (an open one with those words, or a new one through fios.py, its only writer)."""
    p, r, f = m.m("pasta"), m.m("reunioes"), m.m("fios")
    if len(str(titulo or "").strip()) < 4:
        raise ValueError("falta o `titulo` da reunião (ex.: 'Alinhamento NEXOS com o João')")
    data = r.data_valida(data)  # before any pendência is created
    ident = f"{data}-{p.slug(titulo)}"
    ativas = m.m("decisoes").ativas(login)
    dec = [_achar_ref(p, x, ativas, "decisao", "valor") or x for x in r.como_lista(decisoes)]
    abertas = f.abertos(login, 200)
    pend, novas = [], []
    for x in r.como_lista(proximos):
        ref = _achar_ref(p, x, abertas, "pendencia", "titulo")
        if not ref:
            novas.append({"id": uuid.uuid4().hex[:6], "titulo": x[:200], "area": str(area or "").lower() or "geral",
                          "origem": f"reunião {titulo} ({data})", "fontes": [f"reuniao:{ident}"]})
            ref = f"pendencia:{novas[-1]['id']}"
        pend.append(ref)
    if novas:
        f.mesclar(login, novas)
    nota = r.registrar(titulo, data, participantes, resumo, dec, pend, origem="contado por ele no Telegram",
                       por="agente", area=area)
    if nota["efeito"] != "igual":
        p.versionar(f"reunião: {nota['arquivo']}")
    return {**nota, "novas": len(novas)}


def executar(acao: str, login: str, texto: str = "", ref: str = "", titulo: str = "", onde_parou: str = "",
             estado: str = "", area: str = "", secao: str = "", conteudo: str = "", aprovado: str = "", motivo: str = "",
             data: str = "", participantes="", resumo: str = "", decisoes=None, proximos=None) -> str:
    m = mods()
    p = m.m("pasta")
    if not p.ativa(login):
        return "O Segundo Cérebro (a Pasta) é só do Matheus e ainda não está ativo para esta conversa."
    acao = str(acao or "consultar").strip().lower()
    if acao == "consultar":
        achados = p.buscar(texto)
        if not achados:
            return f"Nada na Pasta sobre “{texto}”. Diga que não está registrado (não invente)."
        return "\n".join(f"- [[{a['nota']}]] {a['titulo']}: {a['trecho']}" for a in achados)
    if acao == "assunto":
        a = m.m("assuntos")
        if ref:
            x = a.atualizar(ref, onde_parou=onde_parou, estado=estado, por="agente")
            return f"Assunto atualizado: {a.linha(x)}"
        x = a.registrar(titulo, onde_parou=onde_parou, area=area, estado=estado or "andamento", por="agente")
        p.versionar("assunto")
        return f"Assunto {'atualizado' if x['efeito'] == 'atualizou' else 'aberto'}: {a.linha(x)}"
    if acao in ("reuniao", "reunião"):
        x = reuniao(m, login, titulo, data, participantes, resumo, decisoes, proximos, area)
        efeito = {"nova": "registrada", "atualizou": "completada", "igual": "já estava assim"}[x["efeito"]]
        return (f"Reunião {efeito}: {m.m('reunioes').linha(x)}" +
                (f"; {x['novas']} pendência(s) nova(s) dos próximos passos." if x["novas"] else "."))
    if acao == "assuntos":
        lista = m.m("assuntos").abertos(30)
        return "\n".join("- " + m.m("assuntos").linha(x) for x in lista) or "Nenhum assunto em andamento."
    if acao == "desfazer":
        feito = desfazer(m, ref or "ultimo", motivo, login)
        return f"Desfeito: {', '.join(feito)} (foi para o arquivo morto)." if feito else "Nada encontrado para desfazer."
    if acao == "contexto":
        if secao and conteudo:
            onde = p.gravar_contexto(secao if secao.endswith(".md") else f"{secao}.md", conteudo, aprovado)
            p.versionar(f"contexto: {onde}")
            return f"Gravado em {onde} com o ok dele."
        faltam = p.contexto_pendente()
        alvo = (secao if str(secao).endswith(".md") else f"{secao}.md") if secao else (faltam[0] if faltam else "")
        if not alvo:
            return "Todas as seções de Contexto já foram feitas."
        atual = (p.RAIZ / "Contexto" / alvo).read_text(encoding="utf-8") if (p.RAIZ / "Contexto" / alvo).exists() else ""
        tit, oque = p.CONTEXTO.get(alvo, (alvo, ""))
        return (f"Seção {alvo} ({tit}): {oque}.\nFaltam: {', '.join(faltam) or 'nenhuma'}.\nConteúdo atual:\n{atual[:3000]}\n"
                "Faça as perguntas desta seção uma a uma, leia antes o que já existe (decisões, documentos), resuma e "
                "grave com acao=contexto secao=… conteudo=… aprovado=<as palavras do ok dele>. Perfil: use a ferramenta ficha.")
    if acao == "nota_do_dia":
        nota = m.m("dia").escrever(p)
        return f"Nota do dia gravada (Notas-do-dia/{nota['data']}.md).\n{nota['resumo']}"
    if acao == "auditoria":
        r = m.m("auditoria").gravar(p)
        top = "\n".join(f"- {a['checagem']} · {a['arquivo']}: {a['motivo']} → {a['correcao']}" for a in r["achados"][:12])
        return f"Auditoria: {r['nota']}/100 ({r['arquivo']}).\n{top}"
    return "acao desconhecida: consultar | assunto | assuntos | reuniao | desfazer | contexto | nota_do_dia | auditoria"


class Cerebro(Tool):
    async def execute(self, acao: str = "consultar", texto: str = "", ref: str = "", titulo: str = "",
                      onde_parou: str = "", estado: str = "", area: str = "", secao: str = "", conteudo: str = "",
                      aprovado: str = "", motivo: str = "", data: str = "", participantes="", resumo: str = "",
                      decisoes=None, proximos=None, **kwargs) -> Response:
        try:
            msg = await asyncio.to_thread(executar, acao, dono(self.agent.context), texto, ref, titulo, onde_parou,
                                          estado, area, secao, conteudo, aprovado, motivo, data, participantes, resumo,
                                          decisoes, proximos)
        except (ValueError, KeyError) as exc:
            msg = f"NÃO FEITO: {exc}"
        except Exception as exc:
            msg = f"NÃO FEITO: falha no Segundo Cérebro ({type(exc).__name__}: {str(exc)[:200]})"
        return Response(message=msg, break_loop=False)
