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
import re
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

# Bibliotecas extras embutidas (ex.: python-chess) em scripts/vendor.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

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


    def regiao(self, x1: int, y1: int, x2: int, y2: int, passo: int = 4) -> dict:
        """Estatísticas de cor de um retângulo: média RGB e variação de brilho.

        Variação alta costuma indicar que há algo desenhado (peça, ícone, texto);
        baixa indica fundo liso (casa vazia, botão sem texto)."""
        pts = [self.pixel(x, y) for y in range(int(y1), int(y2), passo) for x in range(int(x1), int(x2), passo)]
        if not pts:
            return {"media": (0, 0, 0), "variacao": 0.0}
        n = len(pts)
        media = tuple(sum(p[i] for p in pts) / n for i in range(3))
        brilho = [sum(p) / 3 for p in pts]
        mb = sum(brilho) / n
        return {"media": tuple(round(v) for v in media), "variacao": round((sum((b - mb) ** 2 for b in brilho) / n) ** 0.5, 1)}

    def grade(self, x1: int, y1: int, x2: int, y2: int, linhas: int, colunas: int, margem: float = 0.15) -> list:
        """Divide um retângulo (tabuleiro, grade de botões) em células e mede cada uma.

        Devolve linhas x colunas de dicts {centro, media, variacao}. `margem` ignora as bordas da célula."""
        cw, ch = (x2 - x1) / colunas, (y2 - y1) / linhas
        out = []
        for r in range(linhas):
            linha = []
            for c in range(colunas):
                cx1, cy1 = x1 + c * cw, y1 + r * ch
                st = self.regiao(cx1 + cw * margem, cy1 + ch * margem, cx1 + cw * (1 - margem), cy1 + ch * (1 - margem))
                linha.append({"centro": (round(cx1 + cw / 2), round(cy1 + ch / 2)), **st})
            out.append(linha)
        return out


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

    def elementos(self) -> list:
        """Árvore da interface (apps comuns): lista de {texto, id, descricao, clicavel, bounds, centro}.

        Não funciona em jogos/telas desenhadas como imagem (vem vazia) — aí use tela()/grade()."""
        self._adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
        xml = self._adb("exec-out", "cat", "/sdcard/ui.xml")
        out = []
        for n in ET.fromstring(xml[xml.find("<"):]).iter("node"):
            m = re.findall(r"\d+", n.get("bounds", ""))
            if len(m) != 4:
                continue
            x1, y1, x2, y2 = map(int, m)
            texto, desc = n.get("text", ""), n.get("content-desc", "")
            if not (texto or desc or n.get("clickable") == "true"):
                continue
            out.append({
                "texto": texto, "descricao": desc, "id": n.get("resource-id", ""),
                "clicavel": n.get("clickable") == "true", "bounds": (x1, y1, x2, y2),
                "centro": ((x1 + x2) // 2, (y1 + y2) // 2),
            })
        return out

    def tocar_texto(self, texto: str, parcial: bool = True):
        """Toca no primeiro elemento cujo texto/descrição contém `texto`."""
        alvo = texto.lower()
        for e in self.elementos():
            rotulo = f"{e['texto']} {e['descricao']}".lower()
            if (alvo in rotulo) if parcial else (alvo in (e["texto"].lower(), e["descricao"].lower())):
                self.tocar(*e["centro"])
                return e
        raise PrecisaLLM(f"não achei '{texto}' na tela")

    def esperar_estavel(self, timeout: float = 5.0, intervalo: float = 0.4) -> Tela:
        """Espera a tela parar de mudar (fim de animação, adversário pensando)."""
        fim, ultimo = time.time() + timeout, None
        while True:
            t = self.tela()
            if ultimo is not None and t.hash == ultimo.hash or time.time() > fim:
                return t
            ultimo = t
            time.sleep(intervalo)

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
