"""Nota do dia (20/10, Q13): at 20h (Bahia) the agent writes Notas-do-dia/AAAA-MM-DD.md with what Matheus decided,
discussed and left to do that day, plus the pendências open for more than 7 days (Q18), and sends a 3-line summary.
Built from the Pasta only (no model): what is not in the Pasta did not happen for the note."""

import time

HORA = 20
VELHA_DIAS = 7


def _no_dia(ts, inicio: float) -> bool:
    try:
        return inicio <= float(ts) < inicio + 86400
    except (TypeError, ValueError):
        return False


def inicio_do_dia(p, ts: float | None = None) -> float:
    t = p.agora_local(ts)
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


def compor(p, ts: float | None = None) -> dict:
    """{data, arquivo, texto, resumo, vazio} for the day of ts."""
    ts = ts or time.time()
    ini = inicio_do_dia(p, ts)
    dia = p.data(ts)
    decisoes = [d for d in p.ler("decisoes") if _no_dia(d.get("em"), ini) and d.get("estado") == "ativa"]
    pendencias = p.ler("pendencias")
    novas = [f for f in pendencias if _no_dia(f.get("criado"), ini) and f.get("dono", "você") == "você"]
    feitas = [f for f in pendencias if f.get("estado") == "resolvido" and _no_dia(f.get("fechado_em") or f.get("atualizado"), ini)]
    velhas = [f for f in pendencias if f.get("estado", "aberto") in ("aberto", "adiado") and f.get("dono", "você") == "você"
              and ts - float(f.get("criado") or ts) > VELHA_DIAS * 86400]
    assuntos = [a for a in p.ler("assuntos") if _no_dia(a.get("atualizado"), ini) and a.get("estado") != "encerrado"]
    # 21/10: a front nobody touched for a week is either forgotten or over; the note asks which
    paradas = sorted((a for a in p.ler("assuntos") if a.get("estado") in ("andamento", "parado")
                      and ts - float(a.get("atualizado") or ts) > VELHA_DIAS * 86400),
                     key=lambda a: float(a.get("atualizado") or 0))
    lk = lambda tipo, x: p.link(f"{tipo}:{x.get('id')}")  # noqa: E731
    partes = [f"# Nota do dia {time.strftime('%d/%m/%Y', p.agora_local(ts))}", ""]
    partes += ["## Decidido"] + ([f"- {lk('decisao', d)} ({d.get('area', 'geral')})" for d in decisoes] or ["- nada"]) + [""]
    partes += ["## Em discussão"] + ([f"- {lk('assunto', a)}: parou em {a.get('onde_parou') or '…'}" for a in assuntos]
                                     or ["- nada"]) + [""]
    partes += ["## Ficou para fazer"] + ([f"- {lk('pendencia', f)}" + (f" (prazo {f['prazo']})" if f.get("prazo") else "")
                                          for f in novas] or ["- nada novo"]) + [""]
    partes += ["## Feito"] + ([f"- {lk('pendencia', f)}" for f in feitas] or ["- nada fechado"]) + [""]
    if velhas:
        partes += [f"## Abertas há mais de {VELHA_DIAS} dias"] + [
            f"- {lk('pendencia', f)} (desde {time.strftime('%d/%m', p.agora_local(float(f.get('criado'))))})"
            for f in sorted(velhas, key=lambda f: float(f.get("criado") or 0))[:15]] + [""]
    if paradas:
        partes += [f"## Frentes sem movimento há mais de {VELHA_DIAS} dias (ainda valem?)"] + [
            f"- {lk('assunto', a)} (parada desde {time.strftime('%d/%m', p.agora_local(float(a.get('atualizado'))))}): "
            f"{a.get('onde_parou') or '…'}" for a in paradas[:10]] + [""]
    texto = p.frontmatter({"status": "fechada", "tags": ["nota-do-dia", dia[:7]]}) + "\n".join(partes).rstrip() + "\n"
    linhas = [f"🧠 Hoje: {len(decisoes)} decisão(ões), {len(assuntos)} assunto(s) andando, "
              f"{len(novas)} pendência(s) nova(s), {len(feitas)} feita(s)."]
    if assuntos:
        a = assuntos[0]
        linhas.append(f"Onde parou: {a.get('titulo')} — {a.get('onde_parou') or '…'}")
    if velhas:
        linhas.append(f"⏳ {len(velhas)} pendência(s) aberta(s) há mais de {VELHA_DIAS} dias, a mais antiga: "
                      f"{velhas[0].get('titulo')}")
    if paradas:
        linhas.append(f"🧭 {len(paradas)} frente(s) sem movimento há {VELHA_DIAS}+ dias, ex.: {paradas[0].get('titulo')}. "
                      "Ainda vale? Responda \"encerra\" ou o que falta.")
    vazio = not (decisoes or assuntos or novas or feitas)
    return {"data": dia, "arquivo": p.RAIZ / "Notas-do-dia" / f"{dia}.md", "texto": texto, "resumo": "\n".join(linhas[:4]),
            "vazio": vazio}


def convite_entrevista(p) -> str:
    faltam = [n for n in p.contexto_pendente() if n != "perfil.md"]
    if not faltam:
        return ""
    tit = p.CONTEXTO[faltam[0]][0]
    return (f"📝 Falta preencher {len(faltam)} parte(s) do seu contexto. Quer fazer agora a de *{tit}* (uns 5 min)? "
            "Responda “bora”.")


def hora_de_escrever(p, ts: float | None = None) -> bool:
    ts = ts or time.time()
    return p.agora_local(ts).tm_hour >= HORA and not (p.RAIZ / "Notas-do-dia" / f"{p.data(ts)}.md").exists()


def escrever(p, ts: float | None = None) -> dict:
    nota = compor(p, ts)
    p.escrever(nota["arquivo"], nota["texto"])
    pasta = p.RAIZ / "Notas-do-dia"
    p.escrever(pasta / "indice.md", "# Notas do dia\n\n" + "\n".join(
        f"- [[Notas-do-dia/{f.stem}]]" for f in sorted(pasta.glob("????-??-??.md"), reverse=True)) + "\n")
    p.versionar(f"nota do dia {nota['data']}")
    return nota
