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


PROXY = "http://host.docker.internal:8787"
MODELOS = {"luna": "openai.gpt-6-luna", "haiku": "us.anthropic.claude-haiku-5-5"}
REVISOR_MODELO = "luna"  # Luna or Haiku 5.5 (never Sol); Luna won the 6-case battery 12/12 vs 11/12


def _modelo(nome: str, pedido: str) -> str:
    """One review call: Luna through the OpenAI-compatible route, Haiku through Bedrock Converse."""
    import urllib.request

    if nome == "haiku":
        url = f"{PROXY}/bedrock/model/{MODELOS['haiku']}/converse"
        body = {"messages": [{"role": "user", "content": [{"text": pedido}]}], "inferenceConfig": {"maxTokens": 8000}}  # it reasons first
    else:
        url = f"{PROXY}/openai/v1/responses"
        body = {"model": MODELOS["luna"], "reasoning": {"effort": "medium"}, "input": [{"role": "user", "content": pedido}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    if nome == "haiku":
        return "".join(c.get("text", "") for c in data.get("output", {}).get("message", {}).get("content", []))
    return "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if c.get("type") == "output_text")

REVISOR = """Você revisa, com olhos novos, uma mensagem que um assistente pessoal de IA quer mandar POR INICIATIVA PRÓPRIA
(ninguém pediu) ao celular do dono. Ela só deve sair se o dono ficaria genuinamente feliz de receber. Confira:
1. Fatos: cada fato, número, data ou nome da mensagem (e do arquivo, se houver) está apoiado no PANORAMA ou no
   ARQUIVO? Nada inventado nem exagerado ("já está aprovado" sem evidência, medida que ninguém citou).
2. Novidade: não é algo já resolvido, já avisado (fios soltos ou iniciativas recentes) nem óbvio para ele.
3. Valor: é concreto e acionável para algo que ele está fazendo de verdade? Uma pessoa ocupada agradeceria?
4. Preferências: respeita os aprendizados sobre o que ele quer ou não receber.
5. Forma: português natural de conversa, até 8 linhas em parágrafos curtos, sem jargão técnico, sem caminhos de
   pasta (/a0/...), termina dizendo o que ele ganha ao tocar em "✅ Bora".
Decida:
- "enviar": está bom como está;
- "ajustar": vale mandar, mas corrija (fato sem apoio sai, texto mais claro/curto) — devolva titulo e texto prontos;
- "descartar": falha em fatos de forma que não dá para corrigir, ou em novidade/valor.
Responda só JSON: {"veredito": "enviar|ajustar|descartar", "motivo": "<uma frase>", "titulo": "<se ajustar>", "texto": "<se ajustar>"}"""


def revisar(login: str, titulo: str, texto: str, tipo: str, arquivo_texto: str = "", modelo: str = "") -> dict:
    """Fresh-context review before an unprompted message goes out. If the reviewer is unreachable the message
    goes as it is (it only reaches its owner) and the result says so."""
    d = carregar(login)
    f = _fios()
    panorama = f.coletar(login, 48)[:18000] if f else ""
    recentes = "\n".join(f"- {e['titulo']}: {e['texto'][:200]}" for e in d["enviadas"][-8:]) or "(nenhuma)"
    pedido = (f"{REVISOR}\n\n# MENSAGEM PROPOSTA (tipo {tipo})\nTítulo: {titulo}\n{texto}\n\n"
              + (f"# ARQUIVO QUE VAI JUNTO (anexado à mensagem; .md/.txt chegam ao celular como PDF)\n{arquivo_texto[:8000]}\n\n" if arquivo_texto else "")
              + "# APRENDIZADOS SOBRE O DONO\n" + ("\n".join(f"- {a}" for a in d["aprendizados"]) or "(nenhum ainda)")
              + f"\n\n# INICIATIVAS JÁ ENVIADAS\n{recentes}\n\n# PANORAMA (o que está acontecendo)\n{panorama}")
    try:
        saida = _modelo(modelo or REVISOR_MODELO, pedido)
        achado = re.search(r"\{.*\}", saida, re.S)
        res = json.loads(achado.group(0), strict=False) if achado else {}
    except Exception as exc:
        return {"veredito": "enviar", "motivo": f"revisor indisponível ({str(exc)[:80]})"}
    veredito = str(res.get("veredito") or "").lower()
    if veredito not in ("enviar", "ajustar", "descartar"):
        return {"veredito": "enviar", "motivo": "revisor sem resposta válida"}
    if veredito == "ajustar" and not (str(res.get("titulo") or "").strip() and str(res.get("texto") or "").strip()):
        veredito = "enviar"
    return {"veredito": veredito, "motivo": str(res.get("motivo") or "")[:300],
            "titulo": str(res.get("titulo") or "").strip()[:80], "texto": str(res.get("texto") or "").strip()[:1500]}


def descartada(login: str, titulo: str, motivo: str) -> None:
    d = carregar(login)
    d.setdefault("descartadas", []).append({"quando": time.time(), "titulo": titulo[:120], "motivo": motivo[:300]})
    d["descartadas"] = d["descartadas"][-30:]
    salvar(login, d)


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
    if d.get("descartadas"):
        partes.append("## O revisor barrou estas (evite o mesmo erro)\n" + "\n".join(
            f"- {x['titulo']}: {x['motivo']}" for x in d["descartadas"][-6:]))
    f = _fios()
    if f:
        partes.append(f.coletar(login, 48, ignorar=ignorar)[:22000])
    partes.append("Próximo passo: pense em 3 a 5 candidatos concretos e chame `iniciativa` acao \"candidatos\" com eles "
                  f"(nota mínima para mandar agora: {nota_minima(login)}).")
    return "\n\n".join(partes)
