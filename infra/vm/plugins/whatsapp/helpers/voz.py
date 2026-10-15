"""Answer in audio when the person spoke (Hermes: gateway/run_voice.py, mode voice_only).

"/voz" turns it on or off, per person (CONFIG). On, when the last message of a phone request was a voice note
(api/receber.py sets the chat's "whatsapp_entrada_audio"), the final answer also goes as a voice note, after the
text: markdown, links, code and emoji taken out, cut at a sentence near LIMITE characters, synthesized by the
auxiliar plugin (Polly, voice Camila, OGG/Opus, the same as the morning summary). The bridge sends a .ogg as a
voice note (Telegram sendVoice; WhatsApp audio).
Off by default: the text already goes, so the audio is one more message on every answer; he turns it on when he
wants it (e.g. driving).
"""

import json
import os
import re
import time
from pathlib import Path

CONFIG = Path("/a0/usr/whatsapp/voz.json")  # {login: true/false}
PASTA = Path("/a0/usr/whatsapp/voz")         # the voice notes (under /a0/usr: the bridge only sends from there)
AUXILIAR = Path("/a0/usr/plugins/auxiliar/helpers/auxiliar.py")
PADRAO = False
LIMITE = 1200      # ~1 min 20 s of speech; Polly takes 3000 (the proxy cuts at 2900)
VIDA = 24 * 3600   # voice notes kept this long
FIM_CORTADO = " O resto está no texto."


def ligada(usuario: str) -> bool:
    try:
        return bool(json.loads(CONFIG.read_text(encoding="utf-8")).get(usuario, PADRAO))
    except (OSError, ValueError, AttributeError):
        return PADRAO


def definir(usuario: str, valor: bool) -> None:
    try:
        dados = json.loads(CONFIG.read_text(encoding="utf-8"))
        dados = dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        dados = {}
    dados[usuario] = bool(valor)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_name(f".{CONFIG.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(dados), encoding="utf-8")
    os.replace(tmp, CONFIG)


def comando(usuario: str, texto: str) -> str | None:
    """The "/voz" command (alone it switches; "/voz on|off" sets): the reply to send, or None when it is not /voz."""
    partes = texto.strip().lower().split()
    if not partes or partes[0].split("@")[0] != "/voz":
        return None
    arg = partes[1] if len(partes) > 1 else ""
    if arg in ("on", "liga", "ligar", "sim"):
        valor = True
    elif arg in ("off", "desliga", "desligar", "nao", "não"):
        valor = False
    else:
        valor = not ligada(usuario)
    definir(usuario, valor)
    return ("🔊 Resposta em áudio ligada: quando você mandar áudio, a resposta vem em texto e também em áudio. "
            "/voz de novo desliga.") if valor else "🔇 Resposta em áudio desligada: só texto. /voz liga de novo."


def quer_audio(usuario: str, ctx) -> bool:
    return bool(usuario) and bool(ctx.get_data("whatsapp_entrada_audio")) and ligada(usuario)


_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")


def texto_falado(texto: str, limite: int = LIMITE) -> str:
    """The answer as it should be spoken: no markdown, links, code or emoji; cut at a sentence near `limite`."""
    t = texto.replace("\r\n", "\n")
    t = re.sub(r"```.*?```", " ", t, flags=re.S)                      # code blocks are read on screen
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)                       # images
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)                    # links: the label only
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"(?:https?://|\bwww\.|/a0/)\S*?(?=[.,;:!?)]*(?:\s|$))", " ", t)  # links and paths are read on screen
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)               # headings
    t = re.sub(r"^\s*>\s?", "", t, flags=re.M)                        # quotes
    t = re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s+", "", t, flags=re.M)        # list markers
    t = re.sub(r"^\s*[-*_|:]{3,}\s*$", "", t, flags=re.M)             # rules, table separators
    t = t.replace("|", ", ")
    t = re.sub(r"(\*\*|__|~~|[*_~])", "", t)                          # bold, italic, strike
    t = _EMOJI.sub("", t)
    linhas = [re.sub(r"\s+", " ", l).strip(" ,") for l in t.split("\n")]
    frases = []
    for l in linhas:
        if l:
            frases.append(l if re.search(r"[.!?:;]$", l) else l + ".")
    t = re.sub(r"\s+([,.!?;:])", r"\1", " ".join(frases)).strip()
    if len(t) <= limite:
        return t
    corte = t[:limite]
    fim = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
    corte = corte[:fim + 1] if fim > limite // 2 else corte.rsplit(" ", 1)[0] + "…"
    return corte + FIM_CORTADO


def _auxiliar():
    import importlib.util
    import sys

    nome = "auxiliar_helper"
    antigo = sys.modules.get(nome)
    mtime = AUXILIAR.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, AUXILIAR)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def idioma_da_resposta(texto: str, entrada: str | None = "") -> str:
    """Language of the spoken answer: Cyrillic text is Russian whatever came in; otherwise the language of the person's
    last voice note (receber stores it), Portuguese by default (15/10: every person in their own language)."""
    letras = [c for c in str(texto or "") if c.isalpha()]
    if letras and sum("\u0400" <= c <= "\u04ff" for c in letras) / len(letras) > 0.3:
        return "ru"
    return str(entrada or "pt")[:5]


def sintetizar(texto: str, destino: Path, idioma: str = "pt") -> str:
    """Text -> OGG/Opus voice note at `destino` (the auxiliar plugin's Polly); '' or the error. Tests replace it."""
    try:
        return _auxiliar().audio(texto, destino, idioma)
    except Exception as exc:
        return f"voz indisponível: {str(exc)[:150]}"


def responder(usuario: str, texto: str, ctx_id: str, enviar, agora: float | None = None, idioma: str | None = "") -> str:
    """Synthesize the answer and send it as a voice note with enviar (ponte.enviar); '' or the reason it did not go."""
    agora = agora or time.time()
    falado = texto_falado(texto)
    if len(falado.split()) < 2:
        return "nada para falar"
    try:
        for velho in PASTA.glob("*.ogg") if PASTA.exists() else []:
            if agora - velho.stat().st_mtime > VIDA:
                velho.unlink(missing_ok=True)
    except OSError:
        pass
    destino = PASTA / f"{re.sub(r'[^A-Za-z0-9_-]', '', ctx_id) or 'resposta'}-{int(agora)}.ogg"
    erro = sintetizar(falado, destino, idioma_da_resposta(falado, idioma))
    if erro:
        return erro
    if not destino.exists():
        return "o áudio não foi gerado"
    return enviar(usuario, "", str(destino), "", None, "resposta")
