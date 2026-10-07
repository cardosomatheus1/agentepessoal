"""Piloto rápido: loop de decisão sem LLM a cada passo.

O LLM entende a tarefa e escreve um script curto usando esta biblioteca:
- `Celular` lê a tela (pixels crus via adb, sem dependências) e age (tocar, deslizar, digitar);
- `jev()` faz perguntas tipadas ao Jev (TypeSafe), que responde em ~0,3 s;
- `PrecisaLLM` encerra o loop quando a situação foge do previsto, para o LLM assumir.

Só biblioteca padrão do Python.
"""

import hashlib
import json
import os
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

SERIAL = os.environ.get("CELULAR_SERIAL", "android:5555")
JEV_URL = os.environ.get("JEV_URL", "http://host.docker.internal:8787/typesafe/v1/systemone")


class PrecisaLLM(Exception):
    """Situação fora do previsto: o loop para e devolve o controle ao LLM."""


# ----------------------------------------------------------------------------- tela

class Tela:
    def __init__(self, raw: bytes):
        w, h, fmt = struct.unpack_from("<III", raw, 0)
        # Android 8+ adds a 4-byte colorspace field to the header.
        header = 16 if len(raw) - 16 == w * h * 4 else 12
        if fmt != 1 or len(raw) - header < w * h * 4:
            raise PrecisaLLM(f"formato de tela inesperado (fmt={fmt}, {w}x{h})")
        self.largura, self.altura = w, h
        self._px = memoryview(raw)[header:]
        self.hash = hashlib.md5(self._px).hexdigest()

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        i = (int(y) * self.largura + int(x)) * 4
        return self._px[i], self._px[i + 1], self._px[i + 2]


def cor_mais_proxima(rgb, paleta: dict) -> tuple:
    """Devolve (rótulo, distância) da cor da paleta mais próxima."""
    best = min(paleta.items(), key=lambda kv: sum((a - b) ** 2 for a, b in zip(rgb, kv[1])))
    return best[0], sum((a - b) ** 2 for a, b in zip(rgb, best[1])) ** 0.5


# --------------------------------------------------------------------------- celular

class Celular:
    def __init__(self, serial: str = SERIAL):
        self.serial = serial
        subprocess.run(["adb", "connect", serial], capture_output=True, timeout=20)

    def _adb(self, *args: str, binario: bool = False):
        out = subprocess.run(["adb", "-s", self.serial, *args], capture_output=True, timeout=30)
        if out.returncode != 0:
            raise PrecisaLLM(f"adb falhou: {' '.join(args)}: {out.stderr.decode(errors='ignore')[:200]}")
        return out.stdout if binario else out.stdout.decode(errors="ignore")

    def tela(self) -> Tela:
        return Tela(self._adb("exec-out", "screencap", binario=True))

    def salvar_print(self, caminho: str = "/a0/tmp/celular.png") -> str:
        with open(caminho, "wb") as f:
            f.write(self._adb("exec-out", "screencap", "-p", binario=True))
        return caminho

    def tocar(self, x, y):
        self._adb("shell", "input", "tap", str(int(x)), str(int(y)))

    def deslizar(self, x1, y1, x2, y2, ms: int = 120):
        self._adb("shell", "input", "swipe", *(str(int(v)) for v in (x1, y1, x2, y2, ms)))

    def digitar(self, texto: str):
        self._adb("shell", "input", "text", texto.replace(" ", "%s"))

    def tecla(self, codigo: int):
        self._adb("shell", "input", "keyevent", str(codigo))

    def abrir(self, pacote: str):
        atividade = self._adb("shell", "cmd", "package", "resolve-activity", "--brief",
                              "-c", "android.intent.category.LAUNCHER", pacote).strip().splitlines()[-1].strip()
        if "/" not in atividade:
            raise PrecisaLLM(f"app {pacote} não encontrado no celular")
        self._adb("shell", "am", "start", "-n", atividade)
        time.sleep(1.5)

    def esperar_mudar(self, antes: str, timeout: float = 2.0) -> Tela:
        """Espera a tela mudar depois de uma ação; devolve a tela nova (ou a mesma, se não mudou)."""
        fim = time.time() + timeout
        while True:
            t = self.tela()
            if t.hash != antes or time.time() > fim:
                return t
            time.sleep(0.15)


# ------------------------------------------------------------------------------- jev

def escolha(instrucoes: str, opcoes) -> dict:
    """Pergunta de escolha. `opcoes`: lista de rótulos ou dict rótulo -> descrição."""
    criterios = opcoes if isinstance(opcoes, dict) else {o: None for o in opcoes}
    return {"type": "choice", "instructions": instrucoes, "criteria": criterios}


def sim_nao(instrucoes: str) -> dict:
    return {"type": "noul", "instructions": instrucoes}


def nota(instrucoes: str, niveis: list) -> dict:
    return {"type": "score", "instructions": instrucoes, "criteria": niveis}


def jev(estado, perguntas: dict, timeout: float = 10.0) -> dict:
    """Envia estado + perguntas tipadas ao Jev e devolve `answers`."""
    body = json.dumps({"model": "jev-latest", "state": estado, "questions": perguntas}).encode()
    req = urllib.request.Request(JEV_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())["answers"]
    except urllib.error.HTTPError as e:
        raise PrecisaLLM(f"Jev indisponível ({e.code}): {e.read().decode(errors='ignore')[:200]}")
    except OSError as e:
        raise PrecisaLLM(f"Jev indisponível: {e}")


def rodar(principal) -> None:
    """Executa a função principal e converte PrecisaLLM em saída clara para o agente."""
    try:
        principal()
    except PrecisaLLM as e:
        print(f"PRECISA_LLM: {e}", flush=True)
        sys.exit(3)
