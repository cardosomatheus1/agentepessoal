"""Initiative: unprompted messages the agent decides to send after looking at everything going on (an idea,
work done ahead, a relevant find, a pattern), with a daily cap and learning from the person's reactions."""

import importlib.util
import json
import re
import sys
import time
import uuid
from pathlib import Path

PASTA = Path("/a0/usr/iniciativa")
LIMITE_DIA = 3          # unprompted messages per day
INTERVALO_MIN = 100 * 60  # at least this long between two of them
TIPOS = ("adiantei", "ideia", "novidade", "padrao", "conexao")


def _login(login: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", (login or "").lower()) or "matheus"


def arquivo(login: str) -> Path:
    return PASTA / f"{_login(login)}.json"


def carregar(login: str) -> dict:
    try:
        d = json.loads(arquivo(login).read_text(encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault("enviadas", [])
    d.setdefault("aprendizados", [])
    return d


def salvar(login: str, d: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    d["enviadas"] = d["enviadas"][-200:]
    d["aprendizados"] = d["aprendizados"][-40:]
    arquivo(login).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def pode_enviar(login: str) -> tuple[bool, str]:
    d = carregar(login)
    hoje = time.strftime("%Y-%m-%d")
    do_dia = [e for e in d["enviadas"] if time.strftime("%Y-%m-%d", time.localtime(e["quando"])) == hoje]
    if len(do_dia) >= LIMITE_DIA:
        return False, f"já foram {LIMITE_DIA} iniciativas hoje"
    if d["enviadas"] and time.time() - d["enviadas"][-1]["quando"] < INTERVALO_MIN:
        return False, "a última iniciativa foi há menos de 100 min"
    return True, ""


def nota_minima(login: str) -> int:
    """4 normally; 3 when nothing went out today and it's afternoon, or when no initiative was ever sent."""
    d = carregar(login)
    if not d["enviadas"]:
        return 3
    hoje = time.strftime("%Y-%m-%d")
    nenhuma_hoje = all(time.strftime("%Y-%m-%d", time.localtime(e["quando"])) != hoje for e in d["enviadas"])
    return 3 if nenhuma_hoje and time.localtime().tm_hour >= 13 else 4


def avaliar(login: str, candidatos: list) -> str:
    """Record what the round thought of and say which one (if any) is worth sending."""
    d = carregar(login)
    validos = []
    for c in candidatos if isinstance(candidatos, list) else []:
        if not isinstance(c, dict) or not str(c.get("titulo") or "").strip():
            continue
        try:
            nota = max(1, min(5, int(c.get("nota") or 0)))
        except (TypeError, ValueError):
            nota = 1
        validos.append({"titulo": str(c["titulo"])[:120], "tipo": str(c.get("tipo") or "ideia"), "nota": nota,
                        "porque": str(c.get("porque") or "")[:300]})
    if len(validos) < 2:
        return "Liste de 3 a 5 candidatos concretos (titulo, tipo, nota de 1 a 5, porque) e chame de novo."
    d.setdefault("pensadas", []).append({"quando": time.time(), "candidatos": validos})
    d["pensadas"] = d["pensadas"][-60:]
    salvar(login, d)
    ok, motivo = pode_enviar(login)
    melhor = max(validos, key=lambda c: c["nota"])
    minima = nota_minima(login)
    if not ok:
        return f"Não mande agora ({motivo}). Responda SEM NOVIDADE."
    if melhor["nota"] < minima:
        return f"Nenhum candidato chegou à nota {minima} (o melhor: «{melhor['titulo']}», {melhor['nota']}). Responda SEM NOVIDADE."
    return (f"Mande «{melhor['titulo']}» (nota {melhor['nota']}, mínimo {minima}). Se for 'adiantei', faça antes o trabalho; "
            "depois chame acao \"enviar\".")


def registrar(login: str, titulo: str, texto: str, tipo: str) -> str:
    d = carregar(login)
    iid = uuid.uuid4().hex[:6]
    d["enviadas"].append({"id": iid, "quando": time.time(), "tipo": tipo if tipo in TIPOS else "ideia",
                          "titulo": titulo, "texto": texto[:1500], "reacao": ""})
    salvar(login, d)
    return iid


def reagir(login: str, iid: str, reacao: str) -> dict | None:
    d = carregar(login)
    item = next((e for e in d["enviadas"] if e["id"] == iid), None)
    if item:
        item["reacao"] = reacao
        item["reagiu_em"] = time.time()
        salvar(login, d)
    return item


def aprender(login: str, texto: str) -> None:
    d = carregar(login)
    texto = re.sub(r"\s+", " ", texto).strip()[:300]
    if texto and texto not in d["aprendizados"]:
        d["aprendizados"].append(texto)
        salvar(login, d)


ESTILO = ("<meta charset='utf-8'><style>body{font-family:'DejaVu Sans',sans-serif;font-size:12pt;line-height:1.45;"
          "margin:1.5cm}h1,h2,h3{color:#1f3a5f}table{border-collapse:collapse}td,th{border:1px solid #bbb;"
          "padding:4px 8px}code{background:#f2f2f2}</style>")


def para_celular(caminho: str) -> tuple[str, str]:
    """(file to send, error). Markdown/text become a PDF next to it, which opens straight on the phone; other
    files go as they are. Only files under /a0/usr can reach the phone."""
    p = Path(str(caminho or "").strip())
    if not p.is_absolute():
        p = Path("/a0/usr/workdir") / p
    try:
        p = p.resolve()
    except OSError:
        return "", "arquivo inválido"
    if not str(p).startswith("/a0/usr/") or not p.is_file():
        return "", f"arquivo não encontrado em /a0/usr: {caminho}"
    if p.suffix.lower() not in (".md", ".txt", ".markdown"):
        return str(p), ""
    import subprocess
    import tempfile

    try:
        import markdown

        corpo = markdown.markdown(p.read_text(encoding="utf-8", errors="replace"), extensions=["tables", "sane_lists"])
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / f"{p.stem}.html"
            html.write_text(ESTILO + corpo, encoding="utf-8")
            subprocess.run(["soffice", "--headless", "--convert-to", "pdf:writer_web_pdf_Export", "--outdir", tmp,
                            str(html)], capture_output=True, timeout=120)
            gerado = Path(tmp) / f"{p.stem}.pdf"
            if not gerado.exists():
                return str(p), ""
            destino = p.with_suffix(".pdf")
            destino.write_bytes(gerado.read_bytes())
            return str(destino), ""
    except Exception:
        return str(p), ""  # the original still goes


def mensagem(titulo: str, texto: str) -> str:
    return f"💡 *{titulo}*\n\n{texto.strip()}"


def botoes(login: str, iid: str) -> list:
    base = f"ini:{_login(login)}:{iid}"
    return [{"id": f"{base}:fazer", "titulo": "✅ Bora"}, {"id": f"{base}:util", "titulo": "👍 Útil"},
            {"id": f"{base}:nao", "titulo": "👎 Dispensa"}]


def _fios():
    nome = "fios_soltos_helper"
    caminho = Path("/a0/usr/plugins/fios_soltos/helpers/fios.py")
    if not caminho.exists():
        return None
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def contexto(login: str, ignorar: str = "") -> str:
    d = carregar(login)
    partes = [f"# Agora: {time.strftime('%A %d/%m/%Y %H:%M')} (America/Bahia)"]
    ok, motivo = pode_enviar(login)
    partes.append("Pode mandar uma iniciativa nesta rodada." if ok else f"NÃO mande iniciativa agora: {motivo}.")
    placar: dict = {}
    for e in d["enviadas"]:
        p = placar.setdefault(e["tipo"], {"util": 0, "fazer": 0, "nao": 0, "sem_reacao": 0})
        p[e.get("reacao") or "sem_reacao"] = p.get(e.get("reacao") or "sem_reacao", 0) + 1
    if placar:
        partes.append("## Como a pessoa reagiu por tipo\n" + "\n".join(
            f"- {t}: 👍 {p['util']} · ✅ {p['fazer']} · 👎 {p['nao']} · sem reação {p['sem_reacao']}" for t, p in placar.items()))
    if d["aprendizados"]:
        partes.append("## O que já se aprendeu sobre o que ela quer (siga)\n" + "\n".join(f"- {a}" for a in d["aprendizados"]))
    if d["enviadas"]:
        partes.append("## Iniciativas recentes (não repita assunto dos últimos 3 dias)\n" + "\n".join(
            f"- {time.strftime('%d/%m %H:%M', time.localtime(e['quando']))} [{e['tipo']}] {e['titulo']} → reação: {e.get('reacao') or 'nenhuma'}"
            for e in d["enviadas"][-15:]))
    f = _fios()
    if f:
        partes.append(f.coletar(login, 48, ignorar=ignorar)[:22000])
    partes.append("Próximo passo: pense em 3 a 5 candidatos concretos e chame `iniciativa` acao \"candidatos\" com eles "
                  f"(nota mínima para mandar agora: {nota_minima(login)}).")
    return "\n\n".join(partes)
