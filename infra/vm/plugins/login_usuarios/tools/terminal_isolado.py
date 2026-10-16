"""Tool `terminal_isolado`: a guest's own computer (16/10). Commands run in the guest's separate container on the host
(infra/vm/caixa_convidados.py), never in the agent's container, so nothing of Matheus's is reachable from it."""

import asyncio
import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

from helpers.tool import Response, Tool

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
SERVICO = "http://host.docker.internal:8790"
SEGREDO = Path("/a0/usr/caixa/segredo.txt")


def convidados():
    nome, caminho = "login_usuarios_convidados", RAIZ / "helpers" / "convidados.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def pedir(acao: str, dados: dict, tempo: int) -> dict:
    req = urllib.request.Request(f"{SERVICO}/{acao}", data=json.dumps(dados).encode(),
                                 headers={"Content-Type": "application/json", "X-Segredo": SEGREDO.read_text().strip()})
    with urllib.request.urlopen(req, timeout=tempo) as r:
        return json.loads(r.read())


class TerminalIsolado(Tool):
    async def execute(self, acao: str = "rodar", comando: str = "", tempo: int = 60, arquivo: str = "",
                      caminho: str = "", **kwargs) -> Response:
        r = lambda m: Response(message=m, break_loop=False)
        sep = sys.modules.get("login_usuarios_separacao")
        login = sep.dono_contexto(self.agent.context) if sep else str(self.agent.context.get_data("dono") or "")
        if not convidados().convidado(login):
            return r("Esta ferramenta é a caixa isolada dos convidados; aqui use o terminal normal do agente.")
        acao = str(acao or "rodar").lower()
        try:
            if acao == "rodar":
                res = await asyncio.to_thread(pedir, "rodar", {"login": login, "comando": comando, "tempo": tempo},
                                              min(int(tempo or 60), 180) + 90)
                if res.get("erro"):
                    return r(f"NÃO RODOU: {res['erro']}")
                return r(f"código de saída {res.get('codigo')}\n{res.get('saida') or '(sem saída)'}")
            if acao == "enviar":
                res = await asyncio.to_thread(pedir, "enviar", {"login": login, "origem": arquivo}, 300)
                return r(f"NÃO FEITO: {res['erro']}" if res.get("erro") else f"Na caixa em {res['na_caixa']}.")
            if acao == "trazer":
                res = await asyncio.to_thread(pedir, "trazer", {"login": login, "caminho": caminho}, 300)
                return r(f"NÃO FEITO: {res['erro']}" if res.get("erro") else
                         f"Copiado para {res['arquivo']} — para mandar à pessoa use whatsapp_enviar com esse arquivo.")
            return r("acao desconhecida: use rodar, enviar ou trazer")
        except Exception as exc:
            return r(f"NÃO FEITO: a caixa não respondeu ({type(exc).__name__}). Tente de novo em instantes.")
