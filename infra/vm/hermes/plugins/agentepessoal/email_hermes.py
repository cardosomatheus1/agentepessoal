"""E-mail para o agente no Hermes (migração, fase 6): o que o A0 faz em whatsapp/extensions/.../_57_email_do_agente.py
(IMAP da caixa dele a cada 2 min, só leitura; só e-mails dele com remetente comprovado viram pedido; o corpo é dado,
nunca ordem), com as MESMAS funções de lá (_novos, _pedido, _na_hora); só a entrega muda: em vez de uma conversa do
A0, um pedido no Hermes (/v1/runs, a sessão do celular dele), seguido até o fim, e a resposta vai ao celular dele.
Roda no relógio (relogio_hermes.py), então só com AGENTEPESSOAL_RELOGIO=1 (até a virada, quem lê o e-mail é o A0)."""
import importlib.util
import json
import logging
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")
API = os.environ.get("HERMES_API_LOCAL", "http://127.0.0.1:8642")
log = logging.getLogger("agentepessoal.email")


def a0():
    """O módulo do A0 (carregado com os módulos mínimos da ponte; a classe Extension dele não é usada)."""
    sys.modules["agentepessoal_ponte_a0"].instalar_modulos()
    nome, caminho = "agentepessoal_email_a0", PLUGINS / "whatsapp" / "extensions" / "python" / "job_loop" / "_57_email_do_agente.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def _api(caminho: str, corpo: dict | None = None) -> dict:
    req = urllib.request.Request(API + caminho, data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": f"Bearer {os.environ.get('API_SERVER_KEY', '')}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


def seguir(run_id: str, dono: str, enviar, espera: float = 6 * 3600, pausa: float = 3.0) -> str:
    fim = time.time() + espera
    while time.time() < fim:
        st = _api(f"/v1/runs/{run_id}")
        if st.get("status") in ("completed", "failed", "cancelled", "stopped"):
            texto = str(st.get("output") or "").strip()
            if texto and not texto.upper().startswith("SEM NOVIDADE"):
                enviar(dono, texto)
            return st["status"]
        time.sleep(pausa)
    return "tempo esgotado"


def passo(m=None, api=None, enviar=None, iniciar=None) -> list:
    """Uma passada: os e-mails novos viram pedidos no Hermes. Devolve os uids entregues."""
    m = m or a0()
    if not m._na_hora(m.MARCA, m.INTERVALO):
        return []
    novos = m._novos()
    feitos = []
    ponte = m._ponte()
    enviar = enviar or (lambda dono, texto: ponte.enviar(dono, texto))
    api = api or _api
    iniciar = iniciar or (lambda alvo, args: threading.Thread(target=alvo, args=args, daemon=True).start())
    for item in novos:
        try:
            texto = m._pedido(item)
            if item.get("anexos") and item.get("confirmado", True):
                texto += "\n\nArquivos do e-mail: " + ", ".join(item["anexos"])
            r = api("/v1/runs", {"input": texto, "session_id": f"tg-{m.DONO}"})
            run_id = r.get("run_id") or r.get("id")
            if not run_id:
                raise RuntimeError(f"o Hermes não abriu o pedido: {str(r)[:120]}")
            iniciar(seguir, (run_id, m.DONO, enviar))
            if item.get("confirmado", True):
                enviar(m.DONO, f"📧 Recebi seu e-mail \"{item['assunto'][:80]}\". Estou cuidando e te respondo aqui.")
            feitos.append(item["uid"])
        except Exception as exc:
            log.warning("email: %s não entregue ao Hermes: %s: %s", item.get("uid"), type(exc).__name__, exc)
    return feitos
