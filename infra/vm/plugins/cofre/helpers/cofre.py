"""Per-person vault: /a0/usr/segredos/<login>.json, values never shown back.

Agent Zero's own secrets (Settings → Secrets) are one store for every login. Here each person
has their own: the agent writes §§secret(NAME); right before the tool runs the placeholder
becomes the owner's value, and any value that comes back in a result is masked again.
"""

import json
import os
import re
from pathlib import Path

PASTA = Path("/a0/usr/segredos")
PADRAO = re.compile(r"§§secret\(([A-Za-z_][A-Za-z0-9_]*)\)")
NOME_OK = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


def _arquivo(usuario: str) -> Path:
    return PASTA / f"{re.sub(r'[^a-z0-9_.-]', '', usuario.lower())}.json"


def carregar(usuario: str) -> dict:
    try:
        return json.loads(_arquivo(usuario).read_text(encoding="utf-8"))
    except Exception:
        return {}


def salvar(usuario: str, nome: str, valor: str) -> None:
    if not usuario or not NOME_OK.match(nome):
        raise ValueError("nome inválido: use MAIÚSCULAS, números e _ (ex.: FACEBOOK_SENHA)")
    dados = carregar(usuario)
    dados[nome] = valor
    _gravar(usuario, dados)


def apagar(usuario: str, nome: str) -> None:
    dados = carregar(usuario)
    dados.pop(nome, None)
    _gravar(usuario, dados)


def _gravar(usuario: str, dados: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    os.chmod(PASTA, 0o700)
    arq = _arquivo(usuario)
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    os.chmod(arq, 0o600)


def trocar(valor, dados: dict):
    """Placeholders -> values, recursively (only the owner's names; others are left as they are)."""
    if isinstance(valor, str):
        return PADRAO.sub(lambda m: dados.get(m.group(1), m.group(0)), valor)
    if isinstance(valor, dict):
        return {k: trocar(v, dados) for k, v in valor.items()}
    if isinstance(valor, list):
        return [trocar(v, dados) for v in valor]
    return valor


def mascarar(texto: str, dados: dict) -> str:
    for nome, valor in sorted(dados.items(), key=lambda kv: -len(kv[1] or "")):
        if valor and len(valor) >= 4:
            texto = texto.replace(valor, f"§§secret({nome})")
    return texto


def dono(context) -> str:
    import sys

    sep = sys.modules.get("login_usuarios_separacao")
    try:
        return sep.dono_contexto(context) if sep else (context.get_data("dono") or "").lower()
    except Exception:
        return ""
