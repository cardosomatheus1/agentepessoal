"""Tool `painel_vivo`: live panels on request (helpers/vivos.py), shown on the Painel page."""

import importlib.util
import json
import sys
from pathlib import Path

from helpers.tool import Response, Tool


def vivos():
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "vivos.py"
    antigo = sys.modules.get("painel_vivos")
    if antigo is None or getattr(antigo, "_mtime", None) != caminho.stat().st_mtime:
        spec = importlib.util.spec_from_file_location("painel_vivos", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = caminho.stat().st_mtime
        sys.modules["painel_vivos"] = m
    return sys.modules["painel_vivos"]


def _dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")) or "matheus"


def _json(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v


class PainelVivo(Tool):
    async def execute(self, acao: str = "listar", id: str = "", titulo: str = "", receita: str = "", hora: str = "06:30",
                      numeros=None, conclusoes=None, tabela=None, **kwargs) -> Response:
        v, login = vivos(), _dono(self.agent.context)
        acao = str(acao or "listar").lower()
        if acao == "criar":
            r = v.criar(login, titulo, receita, hora)
            if not r["ok"]:
                return Response(message=f"Não criei: {r['erro']}", break_loop=False)
            d = r["painel"]
            h, m = d["hora"].split(":")
            return Response(message=(
                f"Painel «{d['titulo']}» criado (id {d['id']}). Agora: 1) crie a rotina que o atualiza, com a ferramenta "
                f"scheduler (create_scheduled_task), nome \"📊 Painel: {d['titulo']}\", todo dia às {d['hora']} "
                f"(minute \"{int(m)}\", hour \"{int(h)}\", timezone America/Bahia) e este prompt:\n{v.prompt_rotina(d)}\n"
                "2) Rode a receita uma vez agora e salve (acao salvar), para ele já ver o painel. 3) Diga a ele que está "
                "no menu → Painel e que se atualiza sozinho antes do resumo da manhã."), break_loop=False)
        if acao == "salvar":
            r = v.salvar(login, id, _json(numeros), _json(conclusoes), _json(tabela))
            return Response(message="Painel atualizado." if r["ok"] else f"Não salvei: {r['erro']}", break_loop=False)
        if acao == "apagar":
            if not str(kwargs.get("pedido_dele") or "").strip():
                return Response(message="Apagar só a pedido dele: mande `pedido_dele` com a fala literal.", break_loop=False)
            return Response(message="Apagado (apague também a rotina \"📊 Painel: …\" no scheduler)." if v.apagar(login, id)
                            else "Esse painel não existe.", break_loop=False)
        lista = v.listar(login)
        if not lista:
            return Response(message="Nenhum painel vivo ainda.", break_loop=False)
        return Response(message="\n".join(
            f"- {d['id']}: {d['titulo']} (às {d['hora']}; " + ("ainda sem leitura" if not d.get("dados") else
                                                                  ("DESATUALIZADO" if d.get("velho") else "em dia")) + ")"
            for d in lista), break_loop=False)
