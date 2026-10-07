"""The virtual Android phone, driven through a persistent uiautomator2 server.

Reading the screen tree through `adb shell uiautomator dump` starts a new
instrumentation every time (~2 s). uiautomator2 keeps one running on the phone and
answers in ~0.1 s. All calls here are blocking; the tool runs them in a thread.
"""

import hashlib
import html
import io
import re
import subprocess
import threading
import time

SERIAL = "android:5555"
_lock = threading.Lock()
_device = None


def _connect(force: bool = False):
    global _device
    import uiautomator2 as u2

    if _device is None or force:
        subprocess.run(["adb", "connect", SERIAL], capture_output=True, timeout=20)
        _device = u2.connect(SERIAL)
    return _device


def device():
    return _connect()


def com_retry(fn):
    """Run fn(device); reconnect once if the phone or the server dropped (e.g. after hibernation)."""
    with _lock:
        try:
            return fn(_connect())
        except Exception:
            return fn(_connect(force=True))


# ------------------------------------------------------------------ screen reading

def arvore(d) -> str:
    return d.dump_hierarchy(compressed=True)


def elementos(xml: str) -> list[dict]:
    out = []
    for node in re.finditer(r"<node [^>]*>", xml):
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', node.group(0)))
        rotulo = html.unescape(attrs.get("text") or attrs.get("content-desc") or "").strip()
        clicavel = attrs.get("clickable") == "true" or attrs.get("long-clickable") == "true"
        editavel = attrs.get("class", "").endswith("EditText")
        if not rotulo and not clicavel and not editavel:
            continue
        b = [int(v) for v in re.findall(r"\d+", attrs.get("bounds", ""))] or [0, 0, 0, 0]
        if b[2] <= b[0] or b[3] <= b[1]:
            continue
        out.append({
            "rotulo": rotulo,
            "id": attrs.get("resource-id", "").split("/")[-1],
            "tipo": "campo" if editavel else ("botão" if clicavel else "texto"),
            "centro": ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2),
            "foco": attrs.get("focused") == "true",
        })
    return out


def texto_da_tela(els: list[dict], limite: int = 60) -> str:
    linhas = []
    for e in els[:limite]:
        nome = e["rotulo"] or (f"[{e['id']}]" if e["id"] else "(sem nome)")
        foco = " (com foco)" if e["foco"] else ""
        linhas.append(f'- {e["tipo"]} "{nome}" em {e["centro"]}{foco}')
    if len(els) > limite:
        linhas.append(f"- … mais {len(els) - limite} itens (use acao=ver com rolagem para o resto)")
    return "\n".join(linhas) if linhas else "(sem texto na tela: jogo, vídeo ou imagem)"


def assinatura(xml: str) -> str:
    return hashlib.md5(xml.encode()).hexdigest()


def miniatura(d) -> bytes:
    """36x64 grayscale thumbnail without the status bar (clock), to compare screens."""
    img = d.screenshot().convert("L")
    img = img.crop((0, int(img.height * 0.04), img.width, img.height)).resize((36, 64))
    return img.tobytes()


def diferenca(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / max(len(a), 1)


def estado(d) -> tuple[str, bytes]:
    return arvore(d), miniatura(d)


def mudou(a: tuple[str, bytes], b: tuple[str, bytes]) -> bool:
    return a[0] != b[0] or diferenca(a[1], b[1]) > 0.3  # idle screen: exactly 0; a 2048 tile move: ~1.5


def esperar_parar(d, antes: tuple[str, bytes], maximo: float = 2.0) -> tuple[str, bool]:
    """Wait until the screen changed and then held still for one poll (or `maximo` s).

    Compares the UI tree and a tiny thumbnail (games and videos have no tree).
    Returns (xml, changed)."""
    time.sleep(0.15)
    fim = time.time() + maximo
    ultimo = estado(d)
    while time.time() < fim:
        time.sleep(0.12)
        atual = estado(d)
        if not mudou(atual, ultimo) and mudou(atual, antes):
            return atual[0], True
        ultimo = atual
    return ultimo[0], mudou(ultimo, antes)


def imagem_pequena(d, largura: int = 360) -> bytes:
    img = d.screenshot()
    img = img.convert("RGB")
    if img.width > largura:
        img = img.resize((largura, round(img.height * largura / img.width)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def abrir(d, pacote: str) -> None:
    """Launch an app. uiautomator2's app_start relies on `monkey`, which fails on this image."""
    out = d.shell(["cmd", "package", "resolve-activity", "--brief", "-c", "android.intent.category.LAUNCHER", pacote]).output
    atividade = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if "/" not in atividade:
        raise ValueError(f"app {pacote} não está instalado")
    d.shell(["am", "start", "-n", atividade])


def app_atual(d) -> str:
    try:
        info = d.app_current()
        return f"{info.get('package', '')}"
    except Exception:
        return ""
