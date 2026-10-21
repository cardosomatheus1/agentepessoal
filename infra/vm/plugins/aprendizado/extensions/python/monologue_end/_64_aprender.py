"""End of a turn in one of Matheus's own chats (phone or app): when the task took many steps, or he corrected the agent,
a background review rereads the task and creates or improves one skill (helpers/aprender.py). Never in scheduled
rounds, trigger chats, subordinates or other people's chats (the skills are shared by every chat of the agent).
He gets one "📚 …" line on the phone when a skill was written."""

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
PLUGINS = RAIZ.parent
DONO = "matheus"
SONNET = "bedrock/converse/us.anthropic.claude-sonnet-5-5"
BEDROCK = "http://host.docker.internal:8787/bedrock"
_TRAVA = threading.Lock()


def carregar(nome: str, caminho: Path):
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def aprender():
    return carregar("aprendizado_aprender", RAIZ / "helpers" / "aprender.py")


def chamar_sonnet(sistema: str, texto: str) -> str:
    """Claude Sonnet 5.5 on Bedrock through the VM proxy (the agent itself may run on Haiku: a skill is worth the
    stronger model)."""
    import litellm

    r = litellm.completion(model=SONNET, api_base=BEDROCK, api_key="proxy", aws_region_name="us-east-1",
                           max_tokens=6000, extra_headers={"X-A0-Dono": DONO},
                           messages=[{"role": "system", "content": sistema}, {"role": "user", "content": texto}])
    return r.choices[0].message.content or ""


def _texto(m) -> str:
    try:
        return m.output_text()
    except Exception:
        c = getattr(m, "content", "")
        return c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)


def tarefa(historia) -> tuple[str, int, str, list[str]]:
    """(text of the current task, tool results in it, his last message, skills loaded in it). The task starts at the
    current topic (Agent Zero opens one at each message of his)."""
    msgs = list(getattr(historia.current, "messages", []) or [])
    passos, fala, carregadas = 0, "", []
    for m in msgs:
        c = getattr(m, "content", None)
        if isinstance(c, dict):
            if "tool_name" in c and "tool_result" in c:
                passos += 1
            if c.get("user_message") or c.get("user_intervention"):
                fala = str(c.get("user_message") or c.get("user_intervention"))
    texto = "\n".join(_texto(m) for m in msgs)
    for nome in __import__("re").findall(r'"skill_name"\s*:\s*\\?"([a-z0-9-]{3,49})', texto):
        if nome not in carregadas:
            carregadas.append(nome)
    return texto, passos, fala, carregadas


def resultados(historia) -> list:
    """The tool results of the current task, in order (for helpers/aprender.contornou)."""
    saida = []
    for m in list(getattr(historia.current, "messages", []) or []):
        c = getattr(m, "content", None)
        if isinstance(c, dict) and "tool_name" in c and "tool_result" in c:
            saida.append(str(c.get("tool_result") or "")[:2000])
    return saida


def _rodar(ctx_id: str, texto: str, carregadas: list[str], login: str) -> None:
    try:
        a = aprender()
        with _TRAVA:  # one review at a time (two chats ending together would race on the same skill)
            r = a.revisar(texto, carregadas, ctx_id, chamar_sonnet)
        print(f"aprendizado: {ctx_id}: {r.get('feito')} {r.get('nome', '')} ({r.get('motivo', '')})", flush=True)
        linha = a.aviso(r)
        if linha and login:
            ponte = sys.modules.get("whatsapp_ponte") or carregar(
                "whatsapp_ponte", PLUGINS / "whatsapp" / "helpers" / "ponte.py")
            ponte.enviar(login, linha, tipo="progresso")
    except Exception as exc:  # never visible to him; the next long task tries again
        print(f"aprendizado: revisão falhou: {type(exc).__name__}: {exc}", flush=True)


class Aprender(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        try:
            a = aprender()
            ctx = self.agent.context
            if not a.ligado() or ctx.get_data("gatilhos_de"):
                return
            if str(ctx.get_data("dono") or ctx.get_data("whatsapp_de") or "").strip().lower() != DONO:
                return
            conversas = carregar("memoria_pessoal_conversas", PLUGINS / "memoria_pessoal" / "helpers" / "conversas.py")
            if conversas.e_rotina(ctx.id):
                return
            texto, passos, fala, carregadas = tarefa(self.agent.history)
            contorno = a.contornou(resultados(self.agent.history)) if hasattr(a, "contornou") else False
            if not a.deve_revisar(passos, fala, a.ultimo(ctx.id), time.time(), contorno=contorno):
                return
            login = str(ctx.get_data("whatsapp_de") or "").strip().lower()
            threading.Thread(target=_rodar, args=(ctx.id, texto, carregadas, login), daemon=True,
                             name="aprendizado").start()
        except Exception as exc:
            print(f"aprendizado: revisão não iniciou: {type(exc).__name__}: {exc}", flush=True)
