"""Gemini watches a public YouTube video straight from its link: nothing is downloaded.

Downloading YouTube videos for Pegasus loaded the VM (a test with parallel downloads pushed the load
average past 130) and took most of the time. Gemini takes the YouTube URL itself.

It runs on Vertex AI, billed to the Google Cloud account whose free-trial credit covers Vertex AI.
The Gemini API through AI Studio is not used: that credit does not pay for it and it would go to the
card. Credentials: none stored. The organization blocks service-account keys, so the VM's AWS role is
federated to the service account agente-video (role Vertex AI User only) and the proxy exchanges it
for a short-lived Google token. Vertex is used only after VERTEX_OK exists, written once the billing report showed the
first test paid by the credit; until then callers fall back to captions.
"""

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

MODELO = "gemini-2.5-flash"
CREDENCIAL = Path("/a0/usr/segredos/vertex_matheus_wif.json")  # AWS→Google federation config (no secret)
PROJETO = "asymmetric-rite-509018-f7"
TOKEN_PROXY = "http://host.docker.internal:8787/arquivos/gcp_token"  # the proxy holds the AWS identity
VERTEX_OK = Path("/a0/usr/segredos/vertex_ok")
API = "https://aiplatform.googleapis.com/v1/projects/{projeto}/locations/global/publishers/google/models/{modelo}:generateContent"
YOUTUBE = re.compile(r"^https?://(www\.|m\.)?(youtube\.com/(watch|shorts/|live/)|youtu\.be/)")
_token = {"valor": "", "ate": 0.0}


def e_youtube(url: str) -> bool:
    return bool(YOUTUBE.match(url or ""))


def liberado() -> bool:
    return CREDENCIAL.is_file() and VERTEX_OK.is_file()


def _token_acesso() -> str:
    """Short-lived Google token from the proxy (AWS role → Workload Identity Federation), cached."""
    if _token["valor"] and time.time() < _token["ate"]:
        return _token["valor"]
    req = urllib.request.Request(TOKEN_PROXY, data=b"{}", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            dados = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"token Google: {e.read().decode(errors='ignore')[:200]}") from None
    _token["valor"], _token["ate"] = dados["token"], float(dados.get("expira") or time.time() + 1800) - 300
    return _token["valor"]


def assistir(url: str, pergunta: str, timeout: int = 300, forcar: bool = False) -> str:
    """Gemini (Vertex AI) watches the whole video, picture and sound, from the link; low media resolution
    keeps it cheap. forcar=True skips the VERTEX_OK gate (the one billing test)."""
    if not CREDENCIAL.is_file():
        raise RuntimeError("Vertex AI não configurado (falta a federação AWS→Google)")
    if not (forcar or VERTEX_OK.is_file()):
        raise RuntimeError("Vertex AI ainda não liberado (aguardando conferir que o crédito cobre o uso)")
    corpo = {"contents": [{"role": "user", "parts": [{"fileData": {"fileUri": url, "mimeType": "video/mp4"}},
                                                     {"text": pergunta}]}],
             "generationConfig": {"temperature": 0, "mediaResolution": "MEDIA_RESOLUTION_LOW"}}
    dados, erro = {}, ""
    for tentativa in range(4):  # Vertex answers 500/503/429 now and then (8 of 10 parallel calls once): retry
        req = urllib.request.Request(API.format(projeto=PROJETO, modelo=MODELO), data=json.dumps(corpo).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {_token_acesso()}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                dados = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            erro = f"Vertex {e.code}: {e.read().decode(errors='ignore')[:300]}"
            if e.code not in (429, 500, 503) or tentativa == 3:
                raise RuntimeError(erro) from None
            time.sleep(8 * (tentativa + 1))
    texto = "".join(p.get("text", "") for c in dados.get("candidates", [])
                    for p in (c.get("content") or {}).get("parts", [])).strip()
    if not texto:
        raise RuntimeError(f"Gemini sem resposta: {json.dumps(dados)[:300]}")
    return texto
