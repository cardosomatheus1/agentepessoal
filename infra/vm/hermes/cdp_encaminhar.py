"""Repasse do CDP do navegador do Hermes (navegador.sh): o Chromium sem tela só escuta no loopback do próprio container
(ignora --remote-debugging-address), então este processo escuta na rede "hermes" (porta 9223) e repassa cada conexão
para 127.0.0.1:9222. Sem mudar nada: o Chromium monta o webSocketDebuggerUrl com o Host pedido (o IP do container), que
volta por aqui. Só a biblioteca padrão.

Com TELA_X=1 (o navegador do Hermes, navegador.sh) o mesmo endereço também atende /tela/* — a tela do "Resolver aqui"
como era no A0 (23/10, Matheus: "no outro agente não tinha problema com Cloudflare"): o Chromium roda COM tela num Xvfb
e o toque do Matheus chega como mouse de verdade do X (xdotool), não como evento sintético do CDP, que o Cloudflare
(Turnstile) recusava; o quadro vem da tela do X (o print por CDP de página com Cloudflare trava com tela, como no A0).
  POST /tela/quadro {"aba", "qualidade"}                -> {"imagem": jpeg base64, "largura", "altura"}
  POST /tela/mouse  {"aba", "acao": toque|segurar|arrastar|rolar, "fx", "fy", "ms", "pontos", "dy"} -> {"ok": true}
As frações (fx, fy) são da área da página, como no portal; a aba vem para a frente antes."""
import base64
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request

DESTINO = ("127.0.0.1", 9222)
ESCUTA = ("0.0.0.0", int(sys.argv[1]) if len(sys.argv) > 1 else 9223)
if len(sys.argv) > 2:  # virada: o mesmo repasse leva o adb da rede do Hermes ao celular (hermes-celular, subir.sh)
    _h, _, _p = sys.argv[2].rpartition(":")
    DESTINO = (_h, int(_p))


def _bombear(origem: socket.socket, destino: socket.socket) -> None:
    try:
        while True:
            dados = origem.recv(65536)
            if not dados:
                break
            destino.sendall(dados)
    except OSError:
        pass
    finally:
        for s in (origem, destino):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


TELA = os.environ.get("TELA_X") == "1"
CDP_LOCAL = "http://127.0.0.1:9222"
_TELA_TRAVA = threading.Lock()  # um gesto por vez: a aba da frente e o ponteiro são um só


def _cdp_json(caminho: str) -> object:
    with urllib.request.urlopen(CDP_LOCAL + caminho, timeout=10) as r:
        texto = r.read().decode() or "null"
    try:
        return json.loads(texto)
    except ValueError:
        return texto


def _avaliar(ws_url: str, expressao: str) -> object:
    from websockets.sync.client import connect

    with connect(ws_url, open_timeout=10, max_size=None) as ws:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expressao, "returnByValue": True}}))
        while True:
            d = json.loads(ws.recv(timeout=10))
            if d.get("id") == 1:
                return ((d.get("result") or {}).get("result") or {}).get("value")


def area_da_pagina(janela: list) -> tuple:
    """(x, y, largura, altura) da área da página na tela do X, de [screenX, screenY, outerWidth, outerHeight,
    innerWidth, innerHeight]: sem gerenciador de janelas, a moldura do Chromium fica toda em cima (abas e endereço)."""
    sx, sy, ow, oh, iw, ih = (int(round(float(v or 0))) for v in janela[:6])
    borda = max(0, (ow - iw) // 2)
    return sx + borda, sy + max(0, oh - ih - borda), iw, ih


def _frente(aba: str) -> tuple:
    alvo = next((t for t in _cdp_json("/json/list") if t.get("id") == aba and t.get("type") == "page"), None)
    if alvo is None:
        raise ValueError("aba não encontrada")
    _cdp_json(f"/json/activate/{aba}")
    time.sleep(0.25)
    janela = _avaliar(alvo["webSocketDebuggerUrl"], "[screenX,screenY,outerWidth,outerHeight,innerWidth,innerHeight]")
    return area_da_pagina(janela or [0] * 6)


def _x(*args: str) -> None:
    subprocess.run(["xdotool", *args], check=True, timeout=20)


def gestos(d: dict, area: tuple) -> list:
    """Os comandos do xdotool de um gesto (testável sem X). O ponteiro chega ao ponto por um ponto do meio, como um
    mouse de verdade; toque aperta e solta com o tempo de um dedo; segurar, o tempo que a pessoa segurou (até 15 s)."""
    x0, y0, w, h = area

    def ponto(fx, fy):
        return (str(x0 + round(max(0.0, min(1.0, float(fx or 0))) * max(1, w - 1))),
                str(y0 + round(max(0.0, min(1.0, float(fy or 0))) * max(1, h - 1))))

    acao = str(d.get("acao") or "")
    if acao in ("toque", "segurar"):
        x, y = ponto(d.get("fx"), d.get("fy"))
        espera = "0.08" if acao == "toque" else str(max(0.5, min(15.0, float(d.get("ms") or 0) / 1000)))
        return [["mousemove", str(int(x) - 12), str(int(y) + 9)], ["sleep", "0.03"], ["mousemove", x, y], ["sleep", "0.05"],
                ["mousedown", "1"], ["sleep", espera], ["mouseup", "1"]]
    if acao == "arrastar":
        pts = [ponto(*p[:2]) for p in (d.get("pontos") or [])][:200]
        if len(pts) < 2:
            raise ValueError("arraste curto")
        cmds = [["mousemove", *pts[0]], ["sleep", "0.05"], ["mousedown", "1"]]
        for x, y in pts[1:]:
            cmds += [["mousemove", x, y], ["sleep", "0.01"]]
        return cmds + [["mouseup", "1"]]
    if acao == "rolar":
        x, y = ponto(0.5, 0.5)
        px = float(d.get("dy") or 0) * h
        n = max(1, min(30, round(abs(px) / 100)))
        return [["mousemove", x, y], ["click", "--repeat", str(n), "--delay", "30", "5" if px > 0 else "4"]]
    raise ValueError("ação desconhecida")


def _tela_responder(cliente: socket.socket, status: int, corpo: dict) -> None:
    dados = json.dumps(corpo).encode()
    cliente.sendall(f"HTTP/1.1 {status} {'OK' if status == 200 else 'Erro'}\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(dados)}\r\nConnection: close\r\n\r\n".encode() + dados)


def _tela(cliente: socket.socket) -> None:
    try:
        cliente.settimeout(15)
        bruto = b""
        while b"\r\n\r\n" not in bruto and len(bruto) < 65536:
            parte = cliente.recv(65536)
            if not parte:
                break
            bruto += parte
        cabeca, _, corpo = bruto.partition(b"\r\n\r\n")
        linhas = cabeca.decode("latin-1").split("\r\n")
        caminho = linhas[0].split(" ")[1] if len(linhas[0].split(" ")) > 1 else ""
        tamanho = next((int(l.split(":", 1)[1]) for l in linhas[1:] if l.lower().startswith("content-length:")), 0)
        while len(corpo) < min(tamanho, 1_000_000):
            parte = cliente.recv(65536)
            if not parte:
                break
            corpo += parte
        d = json.loads(corpo or b"{}")
        with _TELA_TRAVA:
            area = _frente(str(d.get("aba") or ""))
            if caminho == "/tela/quadro":
                from PIL import ImageGrab

                x, y, w, h = area
                img = ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=os.environ.get("DISPLAY", ":99")).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=max(20, min(90, int(d.get("qualidade") or 60))))
                _tela_responder(cliente, 200, {"imagem": base64.b64encode(buf.getvalue()).decode(), "largura": w, "altura": h})
            elif caminho == "/tela/mouse":
                for cmd in gestos(d, area):
                    _x(*cmd)
                _tela_responder(cliente, 200, {"ok": True})
            else:
                _tela_responder(cliente, 404, {"erro": "não existe"})
    except Exception as e:  # o portal cai no caminho antigo (CDP) se a tela falhar
        try:
            _tela_responder(cliente, 502, {"erro": f"{type(e).__name__}: {e}"[:300]})
        except OSError:
            pass
    finally:
        cliente.close()


def _atender(cliente: socket.socket) -> None:
    if TELA:
        try:
            cliente.settimeout(10)
            inicio = cliente.recv(16, socket.MSG_PEEK)
            cliente.settimeout(None)
        except OSError:
            inicio = b""
        if inicio.startswith((b"POST /tela/", b"GET /tela/")):
            _tela(cliente)
            return
    try:
        alvo = socket.create_connection(DESTINO, timeout=10)
        alvo.settimeout(None)
    except OSError:
        cliente.close()
        return
    threading.Thread(target=_bombear, args=(cliente, alvo), daemon=True).start()
    _bombear(alvo, cliente)
    cliente.close()
    alvo.close()


def main() -> None:
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(ESCUTA)
    servidor.listen(64)
    while True:
        cliente, _ = servidor.accept()
        threading.Thread(target=_atender, args=(cliente,), daemon=True).start()


if __name__ == "__main__":
    main()
