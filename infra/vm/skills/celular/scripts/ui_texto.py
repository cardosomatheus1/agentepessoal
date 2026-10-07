"""Lê o XML do uiautomator (stdin) e imprime os textos e botões da tela com a posição de cada um."""
import html
import re
import sys

xml = sys.stdin.read()
itens = []
for node in re.finditer(r"<node [^>]*>", xml):
    attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', node.group(0)))
    rotulo = html.unescape(attrs.get("text") or attrs.get("content-desc") or "")
    clicavel = attrs.get("clickable") == "true"
    if not rotulo and not clicavel:
        continue
    if not rotulo:
        rotulo = attrs.get("resource-id", "").split("/")[-1] or "(sem nome)"
    b = [int(v) for v in re.findall(r"\d+", attrs.get("bounds", ""))] or [0, 0, 0, 0]
    tipo = "botão" if clicavel else "texto"
    itens.append(f'- {tipo} "{rotulo}" em ({(b[0] + b[2]) // 2},{(b[1] + b[3]) // 2})')

if itens:
    print("TELA (texto):")
    print("\n".join(itens[:40]))
else:
    print("TELA: sem texto legível (jogo/imagem) — use o print com vision_load")
