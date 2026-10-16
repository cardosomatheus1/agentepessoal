"""Watches the open conversations with businesses (helpers/externas.py) by code: reads each one in the person's
WhatsApp Web when it is due and, only when the business wrote something new, hands it to the person's phone chat so
the agent answers (the model runs only then). Conversations silent for 3 days are closed and the person is told."""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
ACORDADO_S = 6 * 3600  # keep the VM up this long after the last message of an open conversation
_ESTADO = {"rodando": False, "ultimo": 0.0}


def _carregar(nome: str, caminho: Path):
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def _nome(login: str) -> str:
    conv = sys.modules.get("login_usuarios_convidados")
    return ((conv.convidado(login) or {}).get("nome") if conv else "") or login.title()


async def _responder_por_mim(ex, nav, login: str, nome: str) -> None:
    """16/10: unread chats on the person's WhatsApp become drafts the agent writes and the person approves."""
    if not ex.varrer_agora(login):
        return
    abertos = {p["titulo"] for p in ex.carregar(login).get("pedidos_resposta", []) if p["estado"] in ex.PEDIDOS_ABERTOS}
    try:
        chats = await nav.nao_lidas(ex, login, nome, ex.CHATS_POR_VARREDURA, abertos)
    except Exception as exc:
        print(f"conversas_externas: {login}: sem varredura: {exc}", flush=True)
        return
    d = ex.carregar(login)
    for titulo, mensagens in chats:
        p = ex.novo_pedido(login, titulo, mensagens)
        if p:
            receber = _carregar("whatsapp_receber_vigia", Path("/a0/usr/plugins/whatsapp/api/receber.py"))
            receber._para_a_conversa(login, ex.aviso_pedido(p, nome, d.get("responder_por_mim") or {},
                                                            d.get("exemplos_resposta") or [], ex.contexto_aprendido(login, p)))
            print(f"conversas_externas: {login}: mensagem nova de {titulo} (pedido {p['id']})", flush=True)


async def _passo() -> None:
    ex = _carregar("conversas_externas_helper", RAIZ / "helpers" / "externas.py")
    nav = _carregar("conversas_externas_navegador", RAIZ / "helpers" / "navegador.py")
    for login in ex.logins():
        checar, fechadas = ex.devidas(login)
        nome = _nome(login)
        ponte = None
        if fechadas or checar:
            ponte = _carregar("whatsapp_ponte", Path("/a0/usr/plugins/whatsapp/helpers/ponte.py"))
        for c in fechadas:
            await asyncio.to_thread(ponte.enviar, login, ex.aviso_silencio(c))
        for c in checar:
            try:
                res = await nav.ler(ex, login, nome, c["telefone"])
            except Exception as exc:
                print(f"conversas_externas: {login}/{c['id']} não lida: {exc}", flush=True)
                continue
            novas = ex.registrar_lidas(login, c["id"], res.get("mensagens") or [])
            if novas:
                receber = _carregar("whatsapp_receber_vigia", Path("/a0/usr/plugins/whatsapp/api/receber.py"))
                atual = ex._conversa(ex.carregar(login), c["id"])
                receber._para_a_conversa(login, ex.aviso_ao_agente(atual, novas, nome))
                print(f"conversas_externas: {login}/{c['id']}: {len(novas)} resposta(s) de {c['nome']}", flush=True)
        await _responder_por_mim(ex, nav, login, nome)
        d = ex.carregar(login)
        if (ex.responder_config(d)["ativo"] and ex.HORARIO[0] <= ex._hora_local() < ex.HORARIO[1]) or any(
                c["estado"] in ex.ABERTAS and time.time() - float(c.get("ultima_atividade") or 0) < ACORDADO_S
                for c in d["conversas"]):
            try:
                nav.manter_acordado(ex, login)
            except Exception as exc:
                print(f"conversas_externas: {exc}", flush=True)


class VigiarConversas(Extension):
    async def execute(self, **kwargs):
        if _ESTADO["rodando"] or time.time() - _ESTADO["ultimo"] < 60:
            return
        _ESTADO["rodando"], _ESTADO["ultimo"] = True, time.time()

        async def rodar():
            try:
                await _passo()
            except Exception as exc:
                print(f"conversas_externas: vigia: {type(exc).__name__}: {exc}", flush=True)
            finally:
                _ESTADO["rodando"] = False

        asyncio.get_running_loop().create_task(rodar())
