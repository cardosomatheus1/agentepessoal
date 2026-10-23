"""Áudio do celular no Hermes (migração, fase 6): a ponte manda a mensagem com a marca `[áudio: <caminho>]` (o arquivo
que ela baixou em /a0/usr/whatsapp/<login>/) e, antes do modelo ver o turno, este gancho `pre_llm_call` transcreve com o
mesmo faster-whisper do A0 (whatsapp/api/receber.py: modelo "small", int8, idioma detectado; o usual da pessoa só
quando a detecção não tem certeza) e entrega o texto como contexto do turno: "🎤 [áudio em pt] …".
Só arquivos das pastas do celular; um áudio é transcrito uma vez (memória por caminho)."""
import logging
import re
import subprocess
import sys
import threading

log = logging.getLogger("agentepessoal.audio")
MARCA = re.compile(r"\[áudio: (/[^\]\s]+)\]")
PASTAS = ("/a0/usr/whatsapp/", "/opt/data/agentepessoal/audio_teste/")
MODELO = "small"
CERTEZA_IDIOMA = 0.6
_trava = threading.Lock()
_modelo = {}
_feitos: dict[str, str] = {}


def _whisper():
    with _trava:
        if "m" not in _modelo:
            from faster_whisper import WhisperModel

            _modelo["m"] = WhisperModel(MODELO, device="cpu", compute_type="int8", cpu_threads=4)
        return _modelo["m"]


def transcrever(caminho: str, idioma: str | None = "pt") -> tuple[str, str]:
    import numpy as np

    bruto = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", caminho, "-f", "s16le", "-ac", "1",
                            "-ar", "16000", "-"], capture_output=True, check=True, timeout=120).stdout
    audio = np.frombuffer(bruto, np.int16).astype(np.float32) / 32768.0
    m = _whisper()
    segmentos, info = m.transcribe(audio, language=None, beam_size=1, vad_filter=True)
    texto = " ".join(s.text.strip() for s in segmentos).strip()
    if idioma and info.language != idioma and float(info.language_probability or 0) < CERTEZA_IDIOMA:
        segmentos, _ = m.transcribe(audio, language=idioma, beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segmentos).strip(), idioma
    return texto, info.language


def idioma_da_pessoa(login: str) -> str | None:
    try:
        conv = sys.modules["agentepessoal_acesso"]._convidados().convidado(login)
    except Exception:
        conv = None
    return conv.get("idioma", "pt") if conv else "pt"


def contexto(user_message="", session_id="", task_id="", **kw):
    """Gancho `pre_llm_call`."""
    achados = MARCA.findall(str(user_message or ""))
    if not achados:
        return None
    login = sys.modules["agentepessoal_ponte_a0"].login_da_sessao(str(session_id or task_id or ""))
    partes = []
    for caminho in achados[:3]:
        if not caminho.startswith(PASTAS) or ".." in caminho:
            partes.append(f"(áudio fora da pasta do celular: {caminho})")
            continue
        if caminho not in _feitos:
            try:
                texto, lingua = transcrever(caminho, idioma_da_pessoa(login))
                _feitos[caminho] = f"🎤 [áudio em {lingua}] {texto or '(sem fala)'}"
            except Exception as exc:
                log.warning("audio: %s não transcrito: %s: %s", caminho, type(exc).__name__, exc)
                _feitos[caminho] = "🎤 (não consegui transcrever este áudio; peça para ele escrever ou mandar de novo)"
        partes.append(_feitos[caminho])
    return {"context": "Transcrição do áudio que a pessoa mandou (pode ter erros de transcrição):\n" + "\n".join(partes)}


def registrar(ctx) -> None:
    ctx.register_hook("pre_llm_call", contexto)
