"""Gemini watches a public YouTube video straight from its link: nothing is downloaded.

Downloading YouTube videos for Pegasus loaded the VM (a test with parallel downloads pushed the load
average past 130) and took most of the time. The Gemini API takes the YouTube URL itself. The key is
the owner's GEMINI_API_KEY in the vault (/senha GEMINI_API_KEY ... on Telegram).
"""

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

MODELO = "gemini-2.5-flash"
API = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
COFRE = Path("/a0/usr/segredos/matheus.json")
YOUTUBE = re.compile(r"^https?://(www\.|m\.)?(youtube\.com/(watch|shorts/|live/)|youtu\.be/)")


def e_youtube(url: str) -> bool:
    return bool(YOUTUBE.match(url or ""))


def chave() -> str:
    try:
        return json.loads(COFRE.read_text(encoding="utf-8")).get("GEMINI_API_KEY", "")
    except Exception:
        return ""


def assistir(url: str, pergunta: str, timeout: int = 300) -> str:
    """Gemini watches the whole video (picture and sound) from the link; low media resolution keeps it cheap."""
    k = chave()
    if not k:
        raise RuntimeError("sem GEMINI_API_KEY no cofre")
    corpo = {"contents": [{"parts": [{"file_data": {"file_uri": url}}, {"text": pergunta}]}],
             "generationConfig": {"temperature": 0, "mediaResolution": "MEDIA_RESOLUTION_LOW"}}
    req = urllib.request.Request(API.format(modelo=MODELO), data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": k})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini {e.code}: {e.read().decode(errors='ignore')[:300]}") from None
    texto = "".join(p.get("text", "") for c in dados.get("candidates", [])
                    for p in (c.get("content") or {}).get("parts", [])).strip()
    if not texto:
        raise RuntimeError(f"Gemini sem resposta: {json.dumps(dados)[:300]}")
    return texto
