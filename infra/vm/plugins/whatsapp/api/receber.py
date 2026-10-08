"""A WhatsApp message for the agent, handed over by the host's ponte_whatsapp.

Each person has one chat named "WhatsApp" (created on the first message); "/nova" starts a new
one. Audio is transcribed with the Whisper that ships with Agent Zero (Portuguese) and the chat
shows the transcription. Authenticated by the bridge's shared key, not by login.
"""

import base64
import importlib.util
import secrets
import sys
import time
from pathlib import Path

from helpers.api import ApiHandler, Request, Response

CHAVE = Path("/a0/usr/whatsapp/.chave")
MODELO_WHISPER = "small"  # "base" (the UI default) garbles Portuguese voice notes


def carregar(nome: str, caminho: Path):
    """Load a helper by path, again when the file changed (a deploy), keeping pending state."""
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        if antigo is not None and hasattr(antigo, "PENDENTES"):
            modulo.PENDENTES = antigo.PENDENTES
        sys.modules[nome] = modulo
    return sys.modules[nome]


def ponte():
    """helpers/ponte.py of this plugin (user plugins are not an importable package)."""
    nome = "whatsapp_ponte"
    caminho = Path(__file__).resolve().parents[1] / "helpers" / "ponte.py"
    return carregar(nome, caminho)


def _chave_ok(request: Request) -> bool:
    try:
        esperada = CHAVE.read_text().strip()
    except OSError:
        return False
    return bool(esperada) and secrets.compare_digest(request.headers.get("X-Chave", ""), esperada)


async def _transcrever(caminho: str) -> str:
    from plugins._whisper_stt.helpers import runtime

    dados = base64.b64encode(Path(caminho).read_bytes()).decode()
    resultado = await runtime._transcribe(MODELO_WHISPER, dados, language="pt")
    return str(resultado.get("text") or "").strip()


def _conversa(usuario: str, nova: bool):
    from agent import AgentContext
    from helpers import projects
    from initialize import initialize_agent

    if not nova:
        for ctx in AgentContext.all():
            if ctx.get_data("whatsapp_de") == usuario:
                return ctx, False
    for ctx in AgentContext.all():  # "/nova": the previous one stays as an ordinary chat
        if ctx.get_data("whatsapp_de") == usuario:
            ctx.set_data("whatsapp_de", None)
    ctx = AgentContext(config=initialize_agent(), name="WhatsApp")
    projects.reconcile_agent_profile(ctx, projects.get_context_project_name(ctx))
    ctx.set_data("dono", usuario)
    ctx.set_data("usuario", usuario)
    ctx.set_data("whatsapp_de", usuario)
    return ctx, True


class Receber(ApiHandler):
    @classmethod
    def requires_auth(cls) -> bool:
        return False

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def requires_api_key(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        if not _chave_ok(request):
            return Response('{"erro": "sem acesso"}', status=403, mimetype="application/json")
        from agent import UserMessage
        from helpers import message_queue as mq

        usuario = str(input.get("usuario") or "").lower()
        texto = str(input.get("texto") or "").strip()
        anexos = [str(a) for a in input.get("anexos") or []]
        audio = str(input.get("audio") or "")

        botao = str(input.get("botao") or "")
        if botao.startswith("aprov:"):  # a button of plugins/aprovacoes
            _, ctx_id, pid, decisao = (botao.split(":") + ["", "", "", ""])[:4]
            from agent import AgentContext

            alvo = AgentContext.get(ctx_id)
            rv = sys.modules.get("aprovacoes_revisor")
            if alvo is None or rv is None or ponte().dono(alvo) != usuario or not rv.decidir(ctx_id, decisao, pid):
                ponte().enviar(usuario, "Essa aprovação já não está mais pendente.")
            else:
                ponte().enviar(usuario, {"aprovar": "✅ Aprovado.", "sempre": "✅ Aprovado (e vou permitir sempre).",
                                         "recusar": "❌ Recusado. Não vou fazer."}[decisao])
            return {"ok": True}

        if texto.lower() in ("/nova", "/novo", "nova conversa"):
            ctx, _ = _conversa(usuario, nova=True)
            ponte().enviar(usuario, "🆕 Conversa nova começada. Pode mandar.")
            return {"ok": True, "context": ctx.id}

        if audio:
            try:
                transcrito = await _transcrever(audio)
            except Exception as exc:
                transcrito = ""
                print(f"whatsapp: transcription failed: {exc}", flush=True)
            if transcrito:
                texto = f"🎤 {transcrito}" + (f"\n\n{texto}" if texto else "")
            else:
                anexos.append(audio)
                texto = texto or "(mandei um áudio, mas a transcrição falhou — o arquivo está anexado)"

        ctx, criada = _conversa(usuario, nova=False)
        ctx.set_data("whatsapp_ultima_entrada", time.time())
        nome = str(input.get("nome") or "")
        if nome and not ctx.get_data("usuario_nome"):
            ctx.set_data("usuario_nome", nome)
        mq.log_user_message(ctx, texto, anexos, str(input.get("id") or "") or None, source=" (WhatsApp)")
        ctx.communicate(UserMessage(message=texto, attachments=anexos, id=str(input.get("id") or "")))
        return {"ok": True, "context": ctx.id, "nova": criada}
