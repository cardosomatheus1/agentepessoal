"""Monitors checked by the Radar task: "tell me when <something> happens" in Gmail or Calendar."""

import json
import re
import sys
import time
import uuid
from pathlib import Path

from helpers.tool import Response, Tool

PASTA = Path("/a0/usr/radar")


def _arquivo(login: str) -> Path:
    return PASTA / f"{re.sub(r'[^a-z0-9_.-]', '', login.lower()) or 'matheus'}.json"


def carregar(login: str) -> dict:
    try:
        return json.loads(_arquivo(login).read_text(encoding="utf-8"))
    except Exception:
        return {"monitores": [], "avisados": []}


def salvar(login: str, dados: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    dados["avisados"] = dados.get("avisados", [])[-500:]
    _arquivo(login).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


def dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")) or "matheus"


class Monitor(Tool):
    async def execute(self, acao: str = "listar", fonte: str = "", condicao: str = "", o_que_fazer: str = "",
                      id: str = "", **kwargs) -> Response:
        login = dono(self.agent.context)
        dados = carregar(login)
        acao = str(acao or "listar").lower()
        if acao in ("criar", "adicionar", "add"):
            if not condicao.strip():
                return Response(message="Diga a `condicao` (ex.: e-mail de fulano@x.com com 'nota fiscal').", break_loop=False)
            item = {"id": uuid.uuid4().hex[:6], "fonte": (fonte or "gmail").lower(), "condicao": condicao.strip(),
                    "o_que_fazer": (o_que_fazer or "me avisar com um resumo").strip(), "criado": time.time()}
            dados.setdefault("monitores", []).append(item)
            salvar(login, dados)
            return Response(message=f"Monitor {item['id']} criado: {item['fonte']} — {item['condicao']} → "
                                    f"{item['o_que_fazer']}. O radar confere em cada rodada (08:40 às 20:40).",
                            break_loop=False)
        if acao in ("remover", "apagar", "delete"):
            antes = len(dados.get("monitores", []))
            dados["monitores"] = [m for m in dados.get("monitores", []) if m.get("id") != id]
            salvar(login, dados)
            return Response(message="Removido." if len(dados["monitores"]) < antes else f"Não achei o monitor {id}.",
                            break_loop=False)
        lista = dados.get("monitores", [])
        if not lista:
            return Response(message="Nenhum monitor ativo.", break_loop=False)
        return Response(message="\n".join(f"- {m['id']}: {m['fonte']} — {m['condicao']} → {m['o_que_fazer']}" for m in lista),
                        break_loop=False)
