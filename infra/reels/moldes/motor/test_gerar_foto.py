"""gerar_foto.py checks without calling any provider (CI): crop, the OpenAI streaming read, refusals and the index."""
import base64, io, json, sys, tempfile
from pathlib import Path
from unittest import mock
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gerar_foto as G  # noqa: E402

ok = falhou = 0


def caso(nome, cond):
    global ok, falhou
    if cond: ok += 1
    else: falhou += 1; print("FALHOU:", nome)


def png(w, h):
    b = io.BytesIO(); Image.new("RGB", (w, h), (200, 100, 50)).save(b, "PNG"); return b.getvalue()


class Resposta:
    def __init__(self, linhas): self.linhas = linhas
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self): return iter(l.encode() for l in self.linhas)


def fluxo(dados):
    final = json.dumps({"type": "image_generation.completed", "b64_json": base64.b64encode(dados).decode()})
    parcial = json.dumps({"type": "image_generation.partial_image", "b64_json": "eA=="})
    return Resposta([f"event: x\n", f"data: {parcial}\n", "\n", f"data: {final}\n"])


# crop to the asked proportion, never wider than 1080
caso("1:1 fica 1024", G.recortar(Image.new("RGB", (1024, 1024)), "1:1").size == (1024, 1024))
caso("9:16 de 1024x1536", G.recortar(Image.new("RGB", (1024, 1536)), "9:16").size == (864, 1536))
caso("4:5 de 1024x1536", G.recortar(Image.new("RGB", (1024, 1536)), "4:5").size == (1024, 1280))
caso("16:9 de 1536x1024 cabe em 1080", G.recortar(Image.new("RGB", (1536, 1024)), "16:9").size == (1080, 608))

with tempfile.TemporaryDirectory() as d, mock.patch.object(G, "FOTOS", Path(d)):
    enviado = {}
    def abrir(req, timeout=None):
        enviado.update(json.loads(req.data)); return fluxo(png(1024, 1536))
    with mock.patch.object(G.urllib.request, "urlopen", abrir):
        p = G.gerar("teste_bolo", "bolo de teste", "a cake", "9:16")
    caso("lê a imagem final do fluxo", Image.open(p).size == (864, 1536))
    caso("pede com streaming", enviado.get("stream") is True and enviado.get("partial_images") == 2)
    caso("tamanho vertical", enviado.get("size") == "1024x1536")
    caso("proíbe texto e marca", "No text" in enviado.get("prompt", "") and "brand names" in enviado["prompt"])
    idx = json.loads((Path(d) / "indice.json").read_text())
    caso("registra no índice", idx.get("teste_bolo.jpg") == {"mostra": "bolo de teste", "origem": "gerada (gpt-image-2)"})

    tentativas = []
    def falha(req, timeout=None):
        tentativas.append(1); return Resposta(["data: {\"type\": \"image_generation.partial_image\"}\n"])
    with mock.patch.object(G.urllib.request, "urlopen", falha):
        try: G.gerar("teste_x", "x", "x"); caso("sem imagem final dá erro", False)
        except RuntimeError: caso("sem imagem final dá erro", True)
    caso("tenta 3 vezes", len(tentativas) == 3)
    caso("não grava foto que falhou", not (Path(d) / "teste_x.jpg").exists())

    # 8 photos at once must all land in the index
    with mock.patch.object(G.urllib.request, "urlopen", lambda req, timeout=None: fluxo(png(64, 64))):
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(8) as ex: list(ex.map(lambda i: G.gerar(f"teste_p{i}", f"p{i}", "x"), range(8)))
    idx = json.loads((Path(d) / "indice.json").read_text())
    caso("paralelo não perde registro", all(f"teste_p{i}.jpg" in idx for i in range(8)))

    # and from separate processes (several builders or batches at once)
    import subprocess
    cod = ("import sys,json,base64,io;sys.path.insert(0,%r);import gerar_foto as G;from pathlib import Path;from PIL import Image;"
           "G.FOTOS=Path(%r);b=io.BytesIO();Image.new('RGB',(64,64)).save(b,'PNG');"
           "G._openai=lambda p,r:b.getvalue();[G.gerar(f'teste_q{sys.argv[1]}_{j}','q','x') for j in range(5)]") % (str(Path(G.__file__).parent), d)
    ps = [subprocess.Popen([sys.executable, "-c", cod, str(i)]) for i in range(6)]
    caso("processos terminam", all(p.wait() == 0 for p in ps))
    idx = json.loads((Path(d) / "indice.json").read_text())
    caso("processos não perdem registro", all(f"teste_q{i}_{j}.jpg" in idx for i in range(6) for j in range(5)))

for args, nome in ((("n", "m", "p", "3:2"), "proporção desconhecida"), (("n", "m", "p", "1:1", 11, None, "gemini"), "fonte desconhecida")):
    try: G.gerar(*args); caso(nome, False)
    except ValueError: caso(nome, True)

print(f"{ok}/{ok + falhou}")
sys.exit(1 if falhou else 0)
