#!/usr/bin/env python3
"""Generates a photo with Stable Image Core on Amazon Bedrock (us-west-2, about US$ 0.04 each) and records what it
shows in midia/fotos/indice.json, so a template only uses a photo of what its text talks about (AR Board 13/10:
"a imagem tem de ser do que o texto fala"). The client's own photos always come first; this fills gaps and tests.

    gerar_foto.py <nome> "<o que mostra, em português>" "<prompt em inglês>" [--proporcao 1:1|4:5|9:16|16:9]
"""
import argparse, base64, io, json, sys
from pathlib import Path
import boto3
from PIL import Image

FOTOS = Path(__file__).resolve().parent.parent / "midia" / "fotos"
MODELO, REGIAO, PRECO = "stability.stable-image-core-v1:1", "us-west-2", 0.04
ESTILO = "professional photography, natural light, realistic, sharp, high detail"
NEGATIVO = "text, letters, words, watermark, logo, blurry, deformed, extra fingers, cartoon, illustration, 3d render"


def gerar(nome, mostra, prompt, proporcao="1:1", semente=11, br=None):
    br = br or boto3.client("bedrock-runtime", region_name=REGIAO)
    corpo = {"prompt": f"{prompt}, {ESTILO}"[:9000], "negative_prompt": NEGATIVO, "aspect_ratio": proporcao, "output_format": "jpeg", "seed": semente}
    r = json.loads(br.invoke_model(modelId=MODELO, body=json.dumps(corpo))["body"].read())
    if r.get("finish_reasons") and r["finish_reasons"][0]:
        raise RuntimeError(f"recusada pelo filtro do modelo: {r['finish_reasons'][0]}")
    im = Image.open(io.BytesIO(base64.b64decode(r["images"][0]))).convert("RGB")
    im.thumbnail((1080, 1080 * 16 // 9))
    FOTOS.mkdir(parents=True, exist_ok=True)
    im.save(FOTOS / f"{nome}.jpg", quality=86)
    idx_p = FOTOS / "indice.json"
    idx = json.loads(idx_p.read_text()) if idx_p.exists() else {}
    idx[f"{nome}.jpg"] = {"mostra": mostra, "origem": f"gerada ({MODELO})"}
    idx_p.write_text(json.dumps(dict(sorted(idx.items())), ensure_ascii=False, indent=1))
    return FOTOS / f"{nome}.jpg"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("nome"); ap.add_argument("mostra"); ap.add_argument("prompt")
    ap.add_argument("--proporcao", default="1:1"); a = ap.parse_args()
    print(gerar(a.nome, a.mostra, a.prompt, a.proporcao), f"(~US$ {PRECO:.2f})")
