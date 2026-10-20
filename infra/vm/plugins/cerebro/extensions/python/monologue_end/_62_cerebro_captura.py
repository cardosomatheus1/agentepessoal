"""End of a turn in Matheus's phone chat: the anotação automática (helpers/captura.py) reads what he said and records
Decisões, Pendências and Assuntos in the Pasta, then sends one "📌 Anotei …" line. Background thread: he is not kept
waiting. Never in scheduled rounds, trigger chats, the app's chats or someone else's."""

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_TRAVA = threading.Lock()


def mods():
    nome, caminho = "cerebro_modulos", RAIZ / "helpers" / "modulos.py"
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]


def anotar(ctx_id: str, logs: list, login: str = "matheus") -> dict:
    m = mods()
    p, cv, cap = m.m("pasta"), m.m("conversas"), m.m("captura")
    t = cv.turno(logs)
    dele = [cv.texto_dele(x["texto"]) for x in t["dele"]]
    dele = [x for x in dele if x.strip()]
    if not dele or not t.get("resposta"):
        return {}
    with _TRAVA:
        est = cap.ler_estado(p.RAIZ)
        if est["chats"].get(ctx_id, 0) >= t.get("em", 0):
            return {}
        d, f, a = m.m("decisoes"), m.m("fios"), m.m("assuntos")
        pedido = cap.montar_pedido(dele, t["resposta"], f.abertos(login, 30), a.abertos(20), d.ativas(login))
        propostas = cap.interpretar(cap.chamar(pedido))
        if propostas is None:
            return {}
        r = cap.aplicar(propostas, dele, f"conversa {ctx_id}", d, f, a, login)
        est["chats"][ctx_id] = t.get("em", time.time())
        if r["feito"]:
            est["ultimo"] = [ref for _t, ref, _x in r["feito"]]
            est["ultimo_em"] = time.time()
        p.escrever(cap.estado_arquivo(p.RAIZ), json.dumps(est, ensure_ascii=False))
    linha = cap.aviso(r["feito"])
    if linha:
        m.m("ponte").enviar(login, linha, tipo="progresso")
        p.versionar("anotação automática")
    return r


def _rodar(ctx_id: str, logs: list, login: str) -> None:
    try:
        r = anotar(ctx_id, logs, login)
        if r.get("feito") or r.get("descartados"):
            print(f"cerebro: anotação {ctx_id}: {len(r.get('feito') or [])} feita(s), "
                  f"{len(r.get('descartados') or [])} descartada(s)", flush=True)
    except Exception as exc:  # never visible to him; the next turn tries again
        print(f"cerebro: anotação falhou: {type(exc).__name__}: {exc}", flush=True)


class CerebroCaptura(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        ctx = self.agent.context
        try:
            m = mods()
            login = str(ctx.get_data("whatsapp_de") or "").strip().lower()
            if not login or ctx.get_data("gatilhos_de") or not m.m("pasta").ativa(login):
                return
            if str(ctx.get_data("dono") or login).strip().lower() != login or m.m("conversas").e_rotina(ctx.id):
                return
            threading.Thread(target=_rodar, args=(ctx.id, list(ctx.log.logs), login), daemon=True,
                             name="cerebro-captura").start()
        except Exception as exc:
            print(f"cerebro: anotação não iniciou: {type(exc).__name__}: {exc}", flush=True)
