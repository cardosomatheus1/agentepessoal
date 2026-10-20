"""Tool `delegar` (20/10): Agent Zero hands one task to Hermes or OpenClaw, which run it with their full tools in a
separate box on the host (infra/vm/caixa_delegados.py) and return the answer plus the files they made. The choice of
engine is the agent's or, with motor="auto", helpers/escolha.py; what needs Matheus's accounts never leaves the agent."""

import asyncio
import importlib.util
import json
import sys
import time
import urllib.request
from pathlib import Path

from helpers.tool import Response, Tool

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
SERVICO = "http://host.docker.internal:8791"
SEGREDO = Path("/a0/usr/delegados/segredo.txt")
ESPERA_MAX = 12 * 60  # the tool waits this long at most; longer tasks keep running and are checked with acao=estado
INTERVALO = 15


def escolha():
    nome, caminho = "agent_delegates_escolha", RAIZ / "helpers" / "escolha.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def pedir(acao: str, dados: dict, tempo: int = 120) -> dict:
    req = urllib.request.Request(f"{SERVICO}/{acao}", data=json.dumps(dados).encode(),
                                 headers={"Content-Type": "application/json", "X-Segredo": SEGREDO.read_text().strip()})
    with urllib.request.urlopen(req, timeout=tempo) as r:
        return json.loads(r.read())


def lista_arquivos(arquivos) -> list:
    if isinstance(arquivos, str):
        arquivos = [a.strip() for a in arquivos.replace("\n", ",").split(",") if a.strip()]
    return [str(a).strip() for a in (arquivos or []) if str(a).strip()]


def formatar(res: dict, motivo: str = "") -> str:
    """The delegate's result as the agent reads it: status, tools it really used, files, then its answer marked as
    unverified (the agent checks before passing anything on)."""
    if res.get("erro") and not res.get("status"):
        return f"NÃO DELEGADO: {res['erro']}"
    motor = res.get("motor", "?")
    if res.get("status") == "rodando":
        return (f"{motor} ainda está trabalhando (tarefa {res.get('id')}, {res.get('segundos')} s). Siga com outra coisa "
                f"e confira depois com delegar acao=estado id={res.get('id')} (ou acao=parar).")
    linhas = [f"Delegado a {motor}{f' ({motivo})' if motivo else ''}: {res.get('status')} em {res.get('segundos')} s, "
              f"tarefa {res.get('id')}."]
    usadas = sorted(set(res.get("ferramentas") or []))
    linhas.append("Ferramentas que ele usou: " + (", ".join(usadas) if usadas else "nenhuma"))
    if res.get("erro"):
        linhas.append(f"Problema: {res['erro']}")
    arquivos = res.get("arquivos") or []
    if arquivos:
        linhas.append("Arquivos que ele entregou (já na sua pasta):")
        linhas += [f"- {a['arquivo']} ({a['bytes']} bytes)" for a in arquivos[:40]]
    else:
        linhas.append("Nenhum arquivo entregue.")
    linhas.append("\nResposta do delegado (não verificada: confira os arquivos e os fatos antes de usar ou repassar):\n"
                  + (res.get("resposta") or "(vazia)"))
    return "\n".join(linhas)


class Delegar(Tool):
    async def execute(self, acao: str = "iniciar", motor: str = "auto", tarefa: str = "", arquivos=None,
                      minutos: int = 10, esperar: bool = True, id: str = "", **kwargs) -> Response:
        r = lambda m: Response(message=m, break_loop=False)
        acao = str(acao or "iniciar").strip().lower()
        try:
            if acao in ("estado", "parar"):
                if not str(id or "").strip():
                    return r("Informe `id` da tarefa delegada.")
                return r(formatar(await asyncio.to_thread(pedir, acao, {"id": id})))
            if acao == "listar":
                res = await asyncio.to_thread(pedir, "listar", {})
                itens = res.get("tarefas") or []
                return r("\n".join(f"{t['id']} {t['motor']} {t['status']} ({t['inicio']})" for t in itens)
                         or "Nenhuma tarefa delegada ainda.")
            if acao != "iniciar":
                return r("acao desconhecida: use iniciar, estado, parar ou listar")
            tarefa = str(tarefa or "").strip()
            if not tarefa:
                return r("Escreva a `tarefa`: objetivo, dados necessários e o que entregar em /trabalho/saida/.")
            e = escolha()
            motivo_a0 = e.so_no_a0(tarefa)
            if motivo_a0:
                return r(f"NÃO DELEGADO: esta tarefa {motivo_a0}; isso fica com você (o Hermes e o OpenClaw rodam "
                         "isolados, sem contas, cofre nem mensagens). Se só uma parte precisa disso, faça essa parte e "
                         "delegue o resto sem citar contas ou senhas.")
            motor = str(motor or "auto").strip().lower()
            motivo = "escolhido por você"
            if motor not in ("hermes", "openclaw"):
                motor, motivo = e.escolher_motor(tarefa)
            minutos = max(1, min(int(minutos or 10), 30))
            res = await asyncio.to_thread(pedir, "iniciar", {"motor": motor, "tarefa": tarefa, "minutos": minutos,
                                                             "arquivos": lista_arquivos(arquivos)}, 600)
            if res.get("erro"):
                return r(f"NÃO DELEGADO: {res['erro']}")
            id_ = res["id"]
            if not esperar:
                return r(f"{motor} começou a tarefa {id_} ({motivo}, até {minutos} min). Confira com delegar "
                         f"acao=estado id={id_}.")
            limite = time.time() + min(minutos * 60 + 180, ESPERA_MAX)
            while True:
                await asyncio.sleep(INTERVALO)
                st = await asyncio.to_thread(pedir, "estado", {"id": id_})
                if st.get("status") != "rodando" or time.time() > limite:
                    return r(formatar(st, motivo))
        except Exception as exc:
            return r(f"NÃO FEITO: o serviço dos delegados não respondeu ({type(exc).__name__}). Tente de novo em instantes "
                     "ou faça você mesmo.")
