"""Monitors checked by the Radar task: "tell me when <something> happens" in Gmail or Calendar."""

import fcntl
import json
import os
import re
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from helpers.tool import Response, Tool

PASTA = Path("/a0/usr/radar")


class EstadoIlegivel(RuntimeError):
    pass


def _arquivo(login: str) -> Path:
    return PASTA / f"{re.sub(r'[^a-z0-9_.-]', '', login.lower()) or 'matheus'}.json"


def carregar(login: str) -> dict:
    """12/10 review: an unreadable file was read as "no monitors" and the next change wiped them; now it is an error."""
    arq = _arquivo(login)
    dados = {}
    if arq.exists():
        for tentativa in range(3):
            try:
                dados = json.loads(arq.read_text(encoding="utf-8"))
                if not isinstance(dados, dict):
                    raise ValueError("não é um objeto JSON")
                break
            except (OSError, ValueError) as exc:
                if tentativa == 2:
                    raise EstadoIlegivel(f"{arq.name} ilegível ({str(exc)[:60]})") from None
                time.sleep(0.1)
    dados.setdefault("monitores", [])
    dados.setdefault("avisados", [])
    return dados


@contextmanager
def mudar(login: str):
    """Read → change → write as one step (file lock; the file replaced whole)."""
    PASTA.mkdir(parents=True, exist_ok=True)
    arq = _arquivo(login)
    with open(arq.with_name(arq.name + ".lock"), "a") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)
        try:
            dados = carregar(login)
            yield dados
            dados["avisados"] = dados.get("avisados", [])[-500:]
            fd, tmp = tempfile.mkstemp(dir=PASTA, prefix=f".{arq.name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(dados, f, ensure_ascii=False, indent=1)
                    f.flush()
                    os.fsync(f.fileno())
                os.chmod(tmp, 0o644)
                os.replace(tmp, arq)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        finally:
            fcntl.flock(trava, fcntl.LOCK_UN)


def dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")) or "matheus"


class Monitor(Tool):
    async def execute(self, acao: str = "listar", fonte: str = "", condicao: str = "", o_que_fazer: str = "",
                      id: str = "", **kwargs) -> Response:
        login = dono(self.agent.context)
        try:
            return Response(message=executar(login, acao, fonte, condicao, o_que_fazer, id), break_loop=False)
        except EstadoIlegivel as exc:
            return Response(message=f"Não consegui ler os monitores ({exc}); nada foi mudado.", break_loop=False)


def executar(login: str, acao: str = "listar", fonte: str = "", condicao: str = "", o_que_fazer: str = "",
             id: str = "") -> str:
    acao = str(acao or "listar").lower()
    if acao in ("criar", "adicionar", "add"):
        if not condicao.strip():
            return "Diga a `condicao` (ex.: e-mail de fulano@x.com com 'nota fiscal')."
        item = {"id": uuid.uuid4().hex[:6], "fonte": (fonte or "gmail").lower(), "condicao": condicao.strip(),
                "o_que_fazer": (o_que_fazer or "me avisar com um resumo").strip(), "criado": time.time()}
        with mudar(login) as dados:
            dados["monitores"].append(item)
        return (f"Monitor {item['id']} criado: {item['fonte']} — {item['condicao']} → {item['o_que_fazer']}. "
                "O radar confere em cada rodada (08:40 às 20:40).")
    if acao in ("remover", "apagar", "delete"):
        with mudar(login) as dados:
            antes = len(dados["monitores"])
            dados["monitores"] = [m for m in dados["monitores"] if m.get("id") != id]
            removido = len(dados["monitores"]) < antes
        return "Removido." if removido else f"Não achei o monitor {id}."
    if acao in ("marcar", "avisado", "avisados_marcar"):
        # 27/10: the Radar round wrote "avisados" with write_file/patch, which the Hermes refuses outside /opt/data: the
        # handled ids were never kept and the same e-mail could be told again. Now it goes through here.
        ids = [x for x in re.split(r"[\s,;]+", str(id or "")) if x][:200]
        if not ids:
            return "Diga em `id` os ids de e-mail/evento já tratados (separados por vírgula)."
        with mudar(login) as dados:
            novos = [x for x in ids if x not in dados["avisados"]]
            dados["avisados"].extend(novos)
        return f"{len(novos)} id(s) marcado(s) como avisados ({len(ids) - len(novos)} já estavam)."
    if acao == "avisados":
        av = carregar(login)["avisados"]
        return ("Avisados (últimos 100): " + ", ".join(av[-100:])) if av else "Nenhum id avisado ainda."
    lista = carregar(login)["monitores"]
    if not lista:
        return "Nenhum monitor ativo."
    return "\n".join(f"- {m['id']}: {m['fonte']} — {m['condicao']} → {m['o_que_fazer']}" for m in lista)
