"""List names / save / delete secrets of the logged-in person. Values are write-only."""

import importlib.util
import sys
from pathlib import Path

from helpers.api import ApiHandler, Request, Response


def cofre():
    nome = "cofre_helper"
    caminho = Path(__file__).resolve().parents[1] / "helpers" / "cofre.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _usuario() -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    u = sep.usuario_da_requisicao() if sep else None
    return (u or "matheus").lower()  # single-user installs: the owner


class Cofre(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        c = cofre()
        usuario = _usuario()
        acao = str(input.get("acao") or "listar")
        try:
            if acao == "salvar":
                nome = str(input.get("nome") or "").strip().upper()
                c.salvar(usuario, nome, str(input.get("valor") or ""))
                if str(input.get("para") or "").strip():
                    c.descrever(usuario, nome, str(input["para"]))
            elif acao == "descrever":
                c.descrever(usuario, str(input.get("nome") or "").strip().upper(), str(input.get("para") or ""))
            elif acao == "apagar":
                c.apagar(usuario, str(input.get("nome") or "").strip().upper())
        except ValueError as exc:
            return {"ok": False, "erro": str(exc), "nomes": sorted(c.carregar(usuario))}
        return {"ok": True, "nomes": sorted(c.carregar(usuario)), "descricoes": c.descricoes(usuario)}
