"""Describe many images without loading them into the agent's context.

vision_load keeps images in the conversation, which holds at most `max_embeds`; with more
images the oldest are evicted and agents start reloading them in a loop. This tool sends each
image on its own to the model (through the VM's proxy), keeps only the text answers, writes
them to a notes file and caches them by file content + question.
"""

import asyncio
import base64
import glob
import hashlib
import io
import json
import os
import time
import urllib.request
from pathlib import Path

from helpers.tool import Response, Tool

URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6.1-sol"
EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
PARALELO = 4
MAX_ARQUIVOS = 300
LADO_MAX = 1600

INSTRUCOES = (
    "Você analisa UMA imagem para um relatório. Responda em português, objetivo, em no máximo 6 linhas:\n"
    "1) o que aparece (objeto, local, veículo, caixa, documento);\n"
    "2) TODO texto legível, transcrito exatamente (números de lote, caixa, packing list, placas, etiquetas, datas);\n"
    "3) o que não dá para ler ou está ambíguo.\n"
    "Não invente: se não estiver visível, diga que não está."
)


def _arquivos(caminhos) -> list[Path]:
    if isinstance(caminhos, str):
        caminhos = [c.strip() for c in caminhos.replace("\n", ",").split(",") if c.strip()]
    out: list[Path] = []
    for c in caminhos or []:
        p = Path(str(c))
        if p.is_dir():
            out += sorted(x for x in p.rglob("*") if x.suffix.lower() in EXT)
        elif any(ch in str(c) for ch in "*?["):
            out += sorted(Path(x) for x in glob.glob(str(c), recursive=True) if Path(x).suffix.lower() in EXT)
        elif p.is_file() and p.suffix.lower() in EXT:
            out.append(p)
    vistos, unicos = set(), []
    for p in out:
        if str(p) not in vistos:
            vistos.add(str(p))
            unicos.append(p)
    return unicos


def _jpeg(path: Path) -> bytes:
    from PIL import Image

    img = Image.open(path)
    img = img.convert("RGB")
    img.thumbnail((LADO_MAX, LADO_MAX))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _perguntar(path: Path, pergunta: str, contexto: str) -> str:
    b64 = base64.b64encode(_jpeg(path)).decode()
    texto = f"{INSTRUCOES}\n\nArquivo: {path.name}"
    if contexto:
        texto += f"\nContexto do usuário: {contexto}"
    if pergunta:
        texto += f"\nO que procurar nesta imagem: {pergunta}"
    body = {
        "model": MODELO,
        "reasoning": {"effort": "low"},
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": texto},
            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
        ]}],
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
            partes = [c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                      for c in item.get("content", []) if c.get("type") == "output_text"]
            return " ".join(" ".join(partes).split()) or "(sem resposta)"
        except Exception as exc:
            erro = str(exc)[:200]
            time.sleep(2 * (tentativa + 1))
    return f"(erro ao analisar: {erro})"


class AnalisarImagens(Tool):
    async def execute(self, caminhos=None, pergunta: str = "", contexto: str = "", arquivo_notas: str = "", **kwargs) -> Response:
        arquivos = _arquivos(caminhos or kwargs.get("paths"))
        if not arquivos:
            return Response(message="Nenhuma imagem encontrada nesses caminhos (aceito arquivos, pastas e padrões como /pasta/*.jpg).", break_loop=False)
        excedente = max(0, len(arquivos) - MAX_ARQUIVOS)
        arquivos = arquivos[:MAX_ARQUIVOS]

        chat_dir = Path("/a0/usr/chats") / self.agent.context.id
        notas = Path(arquivo_notas) if arquivo_notas else chat_dir / "notas_imagens.md"
        cache_path = chat_dir / ".cache_analisar_imagens.json"
        try:
            cache = json.loads(cache_path.read_text())
        except Exception:
            cache = {}

        def chave(p: Path) -> str:
            h = hashlib.sha1(p.read_bytes()).hexdigest()
            return hashlib.sha1(f"{h}|{pergunta}|{contexto}".encode()).hexdigest()

        sem = asyncio.Semaphore(PARALELO)
        feitos = {"n": 0}
        resultados: dict[str, str] = {}

        async def um(p: Path):
            k = await asyncio.to_thread(chave, p)
            if k in cache:
                resultados[str(p)] = cache[k]
            else:
                async with sem:
                    txt = await asyncio.to_thread(_perguntar, p, pergunta, contexto)
                resultados[str(p)] = txt
                if not txt.startswith("(erro"):
                    cache[k] = txt
            feitos["n"] += 1
            await self.set_progress(f"analisando imagens: {feitos['n']}/{len(arquivos)}")

        await asyncio.gather(*(um(p) for p in arquivos))

        linhas = [f"# Análise de {len(arquivos)} imagens", f"Pergunta: {pergunta or '(geral)'}", ""]
        for i, p in enumerate(arquivos, 1):
            linhas.append(f"## {i}. {p.name}\n`{p}`\n\n{resultados[str(p)]}\n")
        chat_dir.mkdir(parents=True, exist_ok=True)
        notas.parent.mkdir(parents=True, exist_ok=True)
        notas.write_text("\n".join(linhas), encoding="utf-8")
        try:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False))
        except OSError:
            pass

        resumo = [f"Analisei {len(arquivos)} imagens uma a uma (sem carregá-las no contexto). Notas completas em {notas}.",
                  "Use estas notas para comparar e concluir; NÃO recarregue as imagens com vision_load.", ""]
        orcamento = 24000
        for i, p in enumerate(arquivos, 1):
            linha = f"{i}. {p.name}: {resultados[str(p)]}"
            if orcamento - len(linha) < 0:
                resumo.append(f"… (o resto está em {notas})")
                break
            resumo.append(linha)
            orcamento -= len(linha)
        if excedente:
            resumo.append(f"\nAtenção: {excedente} imagens além do limite de {MAX_ARQUIVOS} ficaram de fora; chame de novo com elas.")
        erros = sum(1 for v in resultados.values() if v.startswith("(erro"))
        if erros:
            resumo.append(f"\n{erros} imagens deram erro; chamar de novo tenta só elas (as outras estão em cache).")
        return Response(message="\n".join(resumo), break_loop=False)
