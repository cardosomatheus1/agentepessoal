"""The work done outside the agent's chats goes to the Pasta by itself (21/10, Matheus: "o que falta não é você que
devia adicionar, ele deveria atualizar sozinho de acordo com o que tem sido feito").

The operator's sessions (Claude Code, any account, working on this repository) end each turn with a Stop hook
(.claude/hooks/cerebro_operador.py) that drops {"sessao", "dele": [his messages], "relato": the operator's answer} into
ENTRADA on the VM. The job loop (extensions/python/job_loop/_63_cerebro_trabalho.py) reads each file with the same
anotação automática as his phone chat (helpers/captura.py: his words for decisions and new to-dos, the report for
the fronts' progress and finished to-dos, every item checked against a literal quote) and sends him the same
"📌 Anotei …" line. Files that were read go to ENTRADA/lidos (kept LIDOS_DIAS days), ones that failed stay for the next
pass, at most TENTATIVAS times."""

import json
import time
from pathlib import Path

ENTRADA = Path("/a0/usr/segundo_cerebro/entrada")
POR_PASSADA = 5
TENTATIVAS = 3
LIDOS_DIAS = 7
DELE_MAX = 8  # his messages per file (the newest)


def pendentes(entrada: Path = None) -> list[Path]:
    entrada = ENTRADA if entrada is None else entrada
    return sorted(entrada.glob("*.json"))[:POR_PASSADA]


def ler(arquivo: Path) -> dict | None:
    try:
        d = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    dele = [str(m) for m in (d.get("dele") or []) if str(m or "").strip()][-DELE_MAX:]
    relato = str(d.get("relato") or "").strip()
    if not dele and not relato:
        return None
    return {"sessao": str(d.get("sessao") or "")[:80], "dele": dele, "relato": relato,
            "login": str(d.get("login") or "matheus").strip().lower(), "tentativas": int(d.get("tentativas") or 0)}


def anotar(entrada: dict, mods, chamar=None) -> dict:
    """One turn of operator work into the Pasta; the same checks as his phone chat."""
    cap, d, f, a = mods.m("captura"), mods.m("decisoes"), mods.m("fios"), mods.m("assuntos")
    login = entrada["login"]
    pedido = cap.montar_pedido(entrada["dele"], entrada["relato"], f.abertos(login, 30), a.abertos(20), d.ativas(login),
                               relato=entrada["relato"])
    propostas = cap.interpretar((chamar or cap.chamar)(pedido))
    if propostas is None:
        raise ValueError("a revisão não devolveu JSON")
    return cap.aplicar(propostas, entrada["dele"], f"operador {entrada['sessao']}", d, f, a, login,
                       relato=[entrada["relato"]])


def processar(mods, entrada_dir: Path = None, chamar=None, avisar=None, agora: float | None = None) -> list[dict]:
    """Read the waiting files (oldest first, at most POR_PASSADA): write, notify, move to lidos/."""
    entrada_dir = ENTRADA if entrada_dir is None else entrada_dir
    agora = time.time() if agora is None else agora
    lidos = entrada_dir / "lidos"
    resultados = []
    for arq in pendentes(entrada_dir):
        dados = ler(arq)
        if dados is None:
            lidos.mkdir(parents=True, exist_ok=True)
            arq.replace(lidos / arq.name)
            continue
        try:
            r = anotar(dados, mods, chamar)
        except Exception as exc:
            dados["tentativas"] += 1
            if dados["tentativas"] >= TENTATIVAS:
                lidos.mkdir(parents=True, exist_ok=True)
                arq.replace(lidos / arq.name)
            else:
                bruto = json.loads(arq.read_text(encoding="utf-8"))
                bruto["tentativas"] = dados["tentativas"]
                arq.write_text(json.dumps(bruto, ensure_ascii=False), encoding="utf-8")
            resultados.append({"arquivo": arq.name, "erro": f"{type(exc).__name__}: {exc}"})
            continue
        lidos.mkdir(parents=True, exist_ok=True)
        arq.replace(lidos / arq.name)
        linha = mods.m("captura").aviso(r["feito"])
        if linha and avisar:
            avisar(dados["login"], linha)
        resultados.append({"arquivo": arq.name, "feito": [ref for _t, ref, _x in r["feito"]],
                           "descartados": r["descartados"]})
    for velho in (lidos.glob("*.json") if lidos.exists() else []):
        try:
            if agora - velho.stat().st_mtime > LIDOS_DIAS * 86400:
                velho.unlink()
        except OSError:
            pass
    return resultados
