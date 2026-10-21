"""What the Pasta hands to whoever works for Matheus, so his decisions hold the same for the agent, the operator and
the reviewers (21/10, Matheus: "pode fazer os dois e pense melhor como otimizar ainda mais tudo que temos no cérebro
pro dia a dia e agente").

- `para_operador`: the start of every operator session (.claude/hooks/cerebro_inicio.py): his decisions in force with
  their text (prohibitions and permissions first), the open fronts with where they stopped and his open to-dos.
- `para_revisor`: the decisions and preferences of one área (raiz: posts, videos, prospecção) for the Crítico and the
  prospecção reviewer, which follow the AR Board criteria and did not see his later decisions (21/10: the Crítico
  blocked the iFood video citing a week-1 criterion that his "nexo" decision had already replaced).
- `relevantes`: the notes of the Pasta that match what he just wrote, for the agent's turn (it should remember without
  having to decide to search)."""

import re

ORDEM = {"proibicao": 0, "permissao": 1, "preferencia": 2, "decisao": 3}
AREAS_REVISOR = {"raiz": ("raiz", "marketing", "conteudo", "prospeccao", "ifood", "instagram", "oferta", "aprovacoes")}


def _curto(t, n: int) -> str:
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def _decisoes(mods, login: str) -> list[dict]:
    return sorted(mods.m("decisoes").ativas(login), key=lambda d: (ORDEM.get(d.get("tipo"), 9), str(d.get("tema"))))


def linha_decisao(d: dict, n: int = 220) -> str:
    return f"- #{d.get('id')} [{d.get('tipo')}] {d.get('tema')}: {_curto(d.get('valor'), n)}"


def para_operador(mods, login: str = "matheus", limite: int = 18000) -> str:
    partes = ["# Segundo Cérebro do Matheus (lido da VM no início desta sessão)",
              "Decisões dele valem até ele mudar: siga sem perguntar de novo. Frentes e pendências: o estado de agora.", ""]
    dec = _decisoes(mods, login)
    partes += [f"## Decisões em vigor ({len(dec)})"] + [linha_decisao(d, 180) for d in dec] + [""]
    frentes = mods.m("assuntos").abertos(15)
    partes += ["## Frentes abertas (onde pararam)"] + [
        f"- [{a.get('id')}] {a.get('titulo')} ({a.get('area', 'geral')}, {a.get('estado')}): {_curto(a.get('onde_parou'), 200)}"
        for a in frentes] + [""]
    pend = mods.m("fios").abertos(login, 20)
    partes += ["## Pendências dele"] + [f"- {mods.m('fios').linha_curta(f)}" for f in pend]
    texto = "\n".join(partes).strip()
    return texto if len(texto) <= limite else texto[:limite] + "\n…(cortado)"


def para_revisor(mods, area: str = "raiz", login: str = "matheus", limite: int = 4000) -> str:
    """'' when there is none. The decisions whose área or tema belongs to `area`."""
    chaves = AREAS_REVISOR.get(area, (area,))
    escolhidas = [d for d in _decisoes(mods, login)
                  if str(d.get("area") or "") == area or str(d.get("tema") or "").split(".")[0] in chaves]
    if not escolhidas:
        return ""
    texto = ("Decisões e preferências do Matheus em vigor (valem ACIMA dos critérios de calibração: se um critério "
             "contradiz uma decisão, siga a decisão):\n" + "\n".join(linha_decisao(d, 260) for d in escolhidas))
    return texto if len(texto) <= limite else texto[:limite] + "\n…"


def relevantes(mods, texto: str, ja: set | None = None, limite: int = 4) -> str:
    """The notes matching his message (local search, no model), minus the ones already in the turn (`ja`: note paths)."""
    texto = str(texto or "").strip()
    if len(texto) < 12:
        return ""
    try:
        achados = mods.m("pasta").buscar(texto)
    except Exception:
        return ""
    lista = achados if isinstance(achados, list) else (achados or {}).get("resultados", [])
    ja = ja or set()
    linhas = []
    for x in lista:
        nota = str(x.get("nota") or "")
        if not nota or nota in ja or nota.startswith(("Notas-do-dia/", "Arquivo-morto/", "Documentos/auditoria")):
            continue
        resumo = x.get("resumo") or x.get("trecho") or x.get("onde_parou") or ""
        linhas.append(f"- [[{nota}]] {_curto(x.get('titulo') or nota, 100)}" + (f": {_curto(resumo, 160)}" if resumo else ""))
        if len(linhas) >= limite:
            break
    if not linhas:
        return ""
    return "Na Pasta, ligado ao que ele acabou de escrever (use se ajudar; o detalhe: `cerebro` acao=consultar):\n" + "\n".join(linhas)
