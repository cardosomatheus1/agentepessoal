"""Os botões e comandos do celular que o A0 tratava sem modelo (whatsapp/api/receber.py), no Hermes (virada, fase 8).

A ponte do host (ponte_whatsapp.py, botao_hermes) roda este arquivo dentro do Hermes da pessoa, com
{"usuario", "botao", "texto"} na entrada, e lê {"ok": ...} na última linha da saída. As funções são as MESMAS do A0
(_botao_fio, _botao_iniciativa, _botao_rascunho, _botao_responder, _botao_aprendizado, _botao_conta, _botao_prospeccao,
_botao_lead, _botao_rotina, _botao_semana; /pendentes, /ajuda, /voz): o receber.py do A0 é carregado com um
`helpers.api` mínimo e só a entrega muda: o que ele entregaria "na conversa" do A0 (`_entregar`) vai à ponte
(POST /conversa), que abre o pedido na sessão da pessoa no Hermes (com os botões de ok e a resposta no celular).

Também usado dentro do gateway (relógio, conversa_externa): `receber()` é o módulo do A0 com essa entrega."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")
RECEBER = PLUGINS / "whatsapp" / "api" / "receber.py"
NOME = "whatsapp_receber_vigia"  # o mesmo nome que conversas_externas usa para carregar o receber.py
PONTE_URL = "http://host.docker.internal:8789"
CHAVE = Path("/a0/usr/whatsapp/.chave")
_aqui = Path(__file__).resolve().parent

# prefixo do botão -> função do receber.py do A0
BOTOES = {"fio:": "_botao_fio", "ini:": "_botao_iniciativa", "rd:": "_botao_rascunho", "rpa:": "_botao_aprendizado",
          "rp:": "_botao_responder", "ct:": "_botao_conta", "pa:": "_botao_prospeccao", "pl:": "_botao_lead",
          "rta:": "_botao_rotina", "cs:": "_botao_semana"}


def _ponte_a0():
    if "agentepessoal_ponte_a0" not in sys.modules:
        spec = importlib.util.spec_from_file_location("agentepessoal_ponte_a0", _aqui / "ponte_a0.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = m
        spec.loader.exec_module(m)
    return sys.modules["agentepessoal_ponte_a0"]


def _api_stub() -> None:
    """`helpers.api` do A0 (o receber.py importa ApiHandler, Request, Response no topo; aqui só existem)."""
    _ponte_a0().instalar_modulos()
    if "helpers.api" in sys.modules:
        return
    api = types.ModuleType("helpers.api")
    api.ApiHandler = type("ApiHandler", (), {})
    api.Request = type("Request", (), {})

    class Response:  # noqa: D401 - o formato do Flask que o receber usa
        def __init__(self, response="", status=200, mimetype=""):
            self.response, self.status, self.mimetype = response, status, mimetype
    api.Response = Response
    sys.modules["helpers.api"] = api
    sys.modules["helpers"].api = api


def conversa(usuario: str, texto: str) -> dict:
    """O que o A0 entregava na conversa da pessoa vira um pedido no Hermes dela (pela ponte)."""
    import urllib.request

    req = urllib.request.Request(f"{PONTE_URL}/conversa", data=json.dumps({"usuario": usuario, "texto": texto}).encode(),
                                 headers={"Content-Type": "application/json", "X-Chave": CHAVE.read_text().strip()})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def _entregar(usuario: str, texto: str, anexos: list, mid: str, fonte: str, audio: bool = False, idioma: str = "") -> dict:
    r = conversa(usuario, texto + (("\n\nArquivos: " + ", ".join(anexos)) if anexos else ""))
    return {"ok": bool(r.get("ok")), "hermes": True}


def receber():
    """O receber.py do A0 (recarregado quando muda), com a entrega no Hermes."""
    _api_stub()
    mtime = RECEBER.stat().st_mtime
    m = sys.modules.get(NOME)
    if m is None or getattr(m, "_mtime", None) != mtime or not getattr(m, "_hermes", False):
        spec = importlib.util.spec_from_file_location(NOME, RECEBER)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[NOME] = m
    m._entregar, m._hermes = _entregar, True
    return m


async def tratar(usuario: str, botao: str = "", texto: str = "") -> dict:
    usuario = str(usuario or "").strip().lower()
    r = receber()
    ext = sys.modules.get("agentepessoal_externas")
    if ext is None:
        spec = importlib.util.spec_from_file_location("agentepessoal_externas", _aqui / "externas_hermes.py")
        ext = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = ext
        spec.loader.exec_module(ext)
    ext.instalar()  # rp:/rpa: usam o WhatsApp Web da pessoa: o navegador do Hermes dela
    for prefixo, funcao in BOTOES.items():
        if botao.startswith(prefixo):
            res = await getattr(r, funcao)(usuario, botao)
            if prefixo == "rp:":  # o envio pelo WhatsApp Web roda numa tarefa à parte: espera ela terminar aqui
                pendentes = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                if pendentes:
                    await asyncio.wait(pendentes, timeout=600)
            return {"ok": bool(res.get("ok", True)) if isinstance(res, dict) else True}
    comando = str(texto or "").strip().lower()
    if comando in ("/pendentes", "/pendencias", "/pendências"):
        pn = r.carregar("whatsapp_painel_api", RECEBER.parent / "painel.py")
        linhas, botoes = pn.esperando(usuario)
        texto_p = ("⏳ *Esperando você*\n" + "\n".join(linhas)) if linhas else "✅ Nada esperando você agora."
        await asyncio.to_thread(r.ponte().enviar, usuario, texto_p, "", "", botoes or None, "resposta", True)
        return {"ok": True}
    if comando in ("/ajuda", "/comandos", "/help"):
        await asyncio.to_thread(r.ponte().enviar, usuario, r.AJUDA)
        return {"ok": True}
    if comando == "/atividade":
        await asyncio.to_thread(r.ponte().enviar, usuario, r._atividade(usuario))
        return {"ok": True}
    if comando == "/painel":  # o texto vai à ponte, que junta o que está rodando, o livro, a saúde e o gasto
        return {"ok": True, "texto": painel(r, usuario)}
    if comando.startswith("/voz"):  # ninguém tinha ligado (voz.json não existe); as respostas vão em texto
        await asyncio.to_thread(r.ponte().enviar, usuario, "🔇 A resposta em áudio ainda não voltou no agente novo: "
                                "respondo em texto (seus áudios eu continuo entendendo).")
        return {"ok": True}
    return {"ok": False, "erro": f"botão/comando desconhecido: {(botao or comando)[:40]}"}


JOBS = Path("/opt/data/cron/jobs.json")


def painel(r, usuario: str) -> str:
    """/painel do A0 (whatsapp/api/painel.py) com as rotinas do cron do Hermes; o "fazendo agora" vem da ponte."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    pn = r.carregar("whatsapp_painel_api", RECEBER.parent / "painel.py")
    saida = []
    linhas, _ = pn.esperando(usuario)
    saida.append("⏳ *Esperando você*\n" + ("\n".join(linhas) if linhas else "Nada."))
    try:
        pr = pn._helper("prospeccao_helper", "/a0/usr/plugins/prospeccao/helpers/prospeccao.py")
        bloco = pr.painel(usuario) if pr and hasattr(pr, "painel") else ""
    except Exception as exc:
        bloco = f"(não consegui ler: {str(exc)[:80]})"
    if bloco:
        saida.append("🎯 *Prospecção*\n" + bloco)
    tarefas = []
    try:
        dados = json.loads(JOBS.read_text(encoding="utf-8"))
        for j in (dados.get("jobs", dados) if isinstance(dados, dict) else dados) or []:
            ligada = j.get("enabled", True) and j.get("state") not in ("paused", "completed")
            estado = ("error" if j.get("last_status") in ("error", "failed") else
                      ("running" if j.get("state") == "running" else ("idle" if ligada else "disabled")))
            nxt = None
            if ligada and j.get("next_run_at"):
                nxt = datetime.fromisoformat(str(j["next_run_at"]).replace("Z", "+00:00"))
            rotulo = {"idle": "ativa", "running": "rodando", "disabled": "pausada", "error": "com erro"}[estado]
            prox = f", próxima {nxt.astimezone(ZoneInfo('America/Bahia')):%d/%m %H:%M}" if nxt else ""
            tarefas.append({"linha": f"• {j.get('name')} — {rotulo}{prox}", "estado": estado,
                            "quando": nxt.timestamp() if nxt else None})
    except Exception as exc:
        tarefas.append({"linha": f"(não consegui ler: {str(exc)[:80]})", "estado": "error", "quando": None})
    saida.append("📅 *Rotinas*\n" + pn.linhas_rotinas(tarefas))
    ultimas = r._atividade(usuario).split("\n", 1)
    saida.append("📝 *Últimas ações importantes*\n" + (ultimas[1] if len(ultimas) > 1 else "Nenhuma registrada."))
    return "\n\n".join(saida)


def _sem_a0() -> None:
    """Fora do gateway (a ponte roda este arquivo): `agent.AgentContext` do A0 vazio (nenhuma conversa do A0 existe)."""
    if "agent" not in sys.modules or not hasattr(sys.modules["agent"], "AgentContext"):
        agent = types.ModuleType("agent")
        agent.AgentContext = type("AgentContext", (), {"get": staticmethod(lambda *a, **k: None),
                                                        "all": staticmethod(lambda: [])})
        agent.UserMessage = type("UserMessage", (), {"__init__": lambda self, **k: self.__dict__.update(k)})
        sys.modules["agent"] = agent


def main() -> int:
    _sem_a0()
    pedido = json.loads(sys.stdin.read() or "{}")
    try:
        res = asyncio.run(tratar(pedido.get("usuario", ""), str(pedido.get("botao") or ""), str(pedido.get("texto") or "")))
    except Exception as exc:
        res = {"ok": False, "erro": f"{type(exc).__name__}: {exc}"[:300]}
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
