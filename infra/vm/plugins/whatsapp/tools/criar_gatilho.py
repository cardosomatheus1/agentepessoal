"""Create, list or delete the person's event triggers.

A trigger is an address (secret URL) that any service can POST to — a form, a store, NEXOS, an
e-mail forwarder, Zapier/Make. Each call wakes the VM if needed and lands in the person's
"Gatilhos" chat with the instruction saved here; the outcome goes to their WhatsApp.
"""

import json
import re
import urllib.request
from pathlib import Path

from helpers.tool import Response, Tool

PASTA = Path("/a0/usr/gatilhos")
CHAVE = Path("/a0/usr/whatsapp/.chave")


def _dono(context) -> str:
    import sys

    sep = sys.modules.get("login_usuarios_separacao")
    try:
        return sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus").lower()
    except Exception:
        return "matheus"


def _url(usuario: str, nome: str) -> str:
    req = urllib.request.Request("http://host.docker.internal:8789/gatilho_url",
                                 data=json.dumps({"usuario": usuario, "nome": nome}).encode(),
                                 headers={"Content-Type": "application/json", "X-Chave": CHAVE.read_text().strip()})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["url"]
    except urllib.error.HTTPError as e:
        return "(indisponível: " + json.loads(e.read()).get("erro", str(e)) + ")"


class CriarGatilho(Tool):
    async def execute(self, acao: str = "criar", nome: str = "", instrucao: str = "", **kwargs) -> Response:
        usuario = _dono(self.agent.context)
        pasta = PASTA / usuario
        acao = (acao or "criar").lower()
        if acao == "listar":
            itens = sorted(p.stem for p in pasta.glob("*.md")) if pasta.exists() else []
            linhas = [f"- {n}: {_url(usuario, n)}" for n in itens]
            return Response(message="Gatilhos:\n" + ("\n".join(linhas) or "(nenhum)"), break_loop=False)
        nome = re.sub(r"[^A-Za-z0-9_-]", "-", nome.strip())[:60].strip("-")
        if not nome:
            return Response(message="Informe `nome` (ex.: novo-lead).", break_loop=False)
        arquivo = pasta / f"{nome}.md"
        if acao == "apagar":
            arquivo.unlink(missing_ok=True)
            return Response(message=f"Gatilho «{nome}» apagado (chamadas a ele passam a chegar sem instrução).",
                            break_loop=False)
        if not instrucao.strip():
            return Response(message="Informe `instrucao`: o que fazer quando o gatilho disparar.", break_loop=False)
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(instrucao.strip(), encoding="utf-8")
        return Response(message=f"Gatilho «{nome}» pronto. Endereço (POST, qualquer conteúdo): {_url(usuario, nome)}\n"
                                "Trate o endereço como senha: quem o tiver dispara o gatilho.", break_loop=False)
