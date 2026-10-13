#!/usr/bin/env python3
"""Generates a photo for the templates and records what it shows in midia/fotos/indice.json, so a template only uses
a photo of what its text talks about (AR Board 13/10: "a imagem tem de ser do que o texto fala"). The client's own
photos always come first; this fills gaps and tests.

Two sources:
- openai (default): gpt-image-2, medium quality, about US$ 0.06 each. Far more natural hands, faces and places than
  the AWS model (side by side 13/10, after Matheus found the AWS photos "bem estranhas"). It invents brand names and
  writing when allowed, so the prompt always forbids them. Needs streaming: a request over 30 s comes back 502 through
  the proxy otherwise. The key comes from OPENAI_API_KEY, or is injected by the proxy.
- aws: Stable Image Core on Amazon Bedrock (us-west-2), about US$ 0.04 each. The fallback.

    gerar_foto.py <nome> "<o que mostra, em português>" "<prompt em inglês>" [--proporcao 1:1|4:5|9:16|16:9] [--fonte openai|aws]
"""
import argparse, base64, fcntl, io, json, os, sys, threading, urllib.request
from pathlib import Path
from PIL import Image

FOTOS = Path(__file__).resolve().parent.parent / "midia" / "fotos"
FONTES = {"openai": ("gpt-image-2", 0.06), "aws": ("stability.stable-image-core-v1:1", 0.04)}
REGIAO = "us-west-2"
ESTILO = "professional photography, natural light, realistic, sharp, high detail"
NEGATIVO = "text, letters, words, watermark, logo, blurry, deformed, extra fingers, cartoon, illustration, 3d render"
REGRAS_OPENAI = ("Realistic professional photo for the Instagram of a small Brazilian business, natural light, natural "
                 "hands and faces. No text, letters, numbers, logos, brand names, names or writing anywhere in the image: "
                 "aprons, signs, boxes, cakes and packaging stay plain.")
# gpt-image-2 sizes; the result is center-cropped to the asked proportion
_TRAVA = threading.Lock()  # several photos at once share one index: this lock for threads, a file lock for processes
TAMANHO = {"1:1": "1024x1024", "4:5": "1024x1536", "9:16": "1024x1536", "16:9": "1536x1024"}


def _openai(prompt, proporcao, url="https://api.openai.com/v1/images/generations"):
    corpo = {"model": FONTES["openai"][0], "prompt": f"{prompt}\n\n{REGRAS_OPENAI}", "size": TAMANHO[proporcao],
             "quality": "medium", "n": 1, "stream": True, "partial_images": 2}
    cab = {"Content-Type": "application/json"}
    if os.environ.get("OPENAI_API_KEY"):
        cab["Authorization"] = "Bearer " + os.environ["OPENAI_API_KEY"]
    erro = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, json.dumps(corpo).encode(), cab), timeout=400) as r:
                for linha in r:
                    linha = linha.decode().strip()
                    if linha.startswith("data:") and "image_generation.completed" in linha:
                        return base64.b64decode(json.loads(linha[5:])["b64_json"])
            erro = "a resposta terminou sem a imagem final"
        except Exception as e:  # 502 from the proxy, timeout, moderation refusal
            erro = getattr(e, "read", lambda: b"")()[:300] or e
    raise RuntimeError(f"OpenAI não gerou a foto: {erro}")


def _aws(prompt, proporcao, semente, br):
    import boto3
    br = br or boto3.client("bedrock-runtime", region_name=REGIAO)
    corpo = {"prompt": f"{prompt}, {ESTILO}"[:9000], "negative_prompt": NEGATIVO, "aspect_ratio": proporcao, "output_format": "jpeg", "seed": semente}
    r = json.loads(br.invoke_model(modelId=FONTES["aws"][0], body=json.dumps(corpo))["body"].read())
    if r.get("finish_reasons") and r["finish_reasons"][0]:
        raise RuntimeError(f"recusada pelo filtro do modelo: {r['finish_reasons'][0]}")
    return base64.b64decode(r["images"][0])


def recortar(im, proporcao):
    """Center crop to the asked proportion (w:h), then fit within 1080 wide."""
    w, h = (int(x) for x in proporcao.split(":"))
    alvo = w / h
    if im.width / im.height > alvo + 0.01:
        nw = round(im.height * alvo); x = (im.width - nw) // 2; im = im.crop((x, 0, x + nw, im.height))
    elif im.width / im.height < alvo - 0.01:
        nh = round(im.width / alvo); y = (im.height - nh) // 2; im = im.crop((0, y, im.width, y + nh))
    if im.width > 1080:
        im = im.resize((1080, round(im.height * 1080 / im.width)), Image.LANCZOS)
    return im


def gerar(nome, mostra, prompt, proporcao="1:1", semente=11, br=None, fonte="openai"):
    if fonte not in FONTES:
        raise ValueError(f"fonte desconhecida: {fonte}")
    if proporcao not in TAMANHO:
        raise ValueError(f"proporção desconhecida: {proporcao}")
    dados = _openai(prompt, proporcao) if fonte == "openai" else _aws(prompt, proporcao, semente, br)
    im = recortar(Image.open(io.BytesIO(dados)).convert("RGB"), proporcao)
    FOTOS.mkdir(parents=True, exist_ok=True)
    im.save(FOTOS / f"{nome}.jpg", quality=86)
    idx_p = FOTOS / "indice.json"
    with _TRAVA, open(FOTOS / ".indice.trava", "w") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)
        idx = json.loads(idx_p.read_text()) if idx_p.exists() else {}
        idx[f"{nome}.jpg"] = {"mostra": mostra, "origem": f"gerada ({FONTES[fonte][0]})"}
        tmp = idx_p.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(sorted(idx.items())), ensure_ascii=False, indent=1))
        tmp.replace(idx_p)
    return FOTOS / f"{nome}.jpg"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("nome"); ap.add_argument("mostra"); ap.add_argument("prompt")
    ap.add_argument("--proporcao", default="1:1"); ap.add_argument("--fonte", default="openai", choices=list(FONTES))
    a = ap.parse_args()
    print(gerar(a.nome, a.mostra, a.prompt, a.proporcao, fonte=a.fonte), f"(~US$ {FONTES[a.fonte][1]:.2f})")
