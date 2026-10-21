"""Tests of the video plugin's Gemini helper without network (Vertex mocked). Run from the repository root:
python3 infra/operador/rodar_suites_locais.py video"""

import asyncio
import base64
import importlib.util
import json
import sys
import tempfile
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _g():
    spec = importlib.util.spec_from_file_location("video_gemini_teste", RAIZ / "helpers" / "gemini.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Suite:
    def __init__(self):
        self.resultados = []

    def t_ouvir_manda_o_audio_inline_e_pede_os_tempos(self):
        # 21/10: the Crítico gets a Reel's narration (plugins/conteudo material_do_video)
        g = _g()
        partes_enviadas = []
        g._gerar = lambda partes, timeout, forcar: partes_enviadas.append(partes) or "[0.6s] Pediu pelo iFood?"
        audio = Path(tempfile.mkdtemp()) / "narracao.mp3"
        audio.write_bytes(b"ID3fake")
        ok(g.ouvir(str(audio)) == "[0.6s] Pediu pelo iFood?", "devolve a transcrição")
        inline = partes_enviadas[0][0]["inlineData"]
        ok(inline["mimeType"] == "audio/mpeg" and base64.b64decode(inline["data"]) == b"ID3fake", "áudio inline, mp3")
        ok("[12.3s]" in partes_enviadas[0][1]["text"], "pede cada frase com o segundo em que começa")
        grande = audio.with_name("grande.mp3")
        grande.write_bytes(b"0" * (16 * 1024 * 1024))
        try:
            g.ouvir(str(grande))
            raise Falha("áudio grande demais devia ser recusado")
        except RuntimeError:
            pass

    def t_assistir_continua_pelo_link(self):
        g = _g()
        partes_enviadas = []
        g._gerar = lambda partes, timeout, forcar: partes_enviadas.append((partes, forcar)) or "ok"
        g.assistir("https://youtu.be/x", "do que fala?", forcar=True)
        partes, forcar = partes_enviadas[0]
        ok(partes[0]["fileData"]["fileUri"] == "https://youtu.be/x" and forcar, "o vídeo do YouTube segue pelo link")

    def t_sem_vertex_liberado_recusa(self):
        g = _g()
        g.CREDENCIAL = Path("/nao/existe")
        try:
            g.ouvir(__file__)
            raise Falha("sem Vertex configurado devia recusar")
        except RuntimeError as exc:
            ok("Vertex" in str(exc), str(exc))

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print(("✓ " if x["ok"] else "✗ ") + x["teste"] + ("" if x["ok"] else f": {x['erro']}"))
    sys.exit(0 if r["passou"] == r["total"] else 1)
