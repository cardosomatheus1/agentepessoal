"""Temporary files that pile up inside the agent container (20/10: /tmp reached 6.7 GB of build leftovers and the
package caches 2.8 GB; the VM disk hit 89%). Once a week: an entry of /tmp untouched for 3+ days goes (the NEWEST file
inside counts, so a folder still in use stays), and the package-manager caches are emptied (they come back on the next
install). Never the user's files: /a0/usr is not here. Plain functions, tested in tests/suite.py."""

import os
import shutil
import time
from pathlib import Path

TMP = Path("/tmp")
CACHES = [Path("/root/.cache/uv"), Path("/root/.cache/pip"), Path("/root/.npm/_cacache")]
DIAS = 3
POUPAR = {"models"}  # /tmp/models: speech models, slow to download again


def mais_novo(caminho: Path, limite: int = 20000) -> float:
    """Newest mtime of a file or of anything inside a folder (looks at most `limite` entries; when it gives up, the
    folder counts as new, so it stays)."""
    try:
        mais = caminho.lstat().st_mtime
    except OSError:
        return time.time()
    if not caminho.is_dir() or caminho.is_symlink():
        return mais
    vistos = 0
    for raiz, pastas, arquivos in os.walk(caminho):
        for nome in pastas + arquivos:
            vistos += 1
            if vistos > limite:
                return time.time()
            try:
                mais = max(mais, os.lstat(os.path.join(raiz, nome)).st_mtime)
            except OSError:
                continue
    return mais


def escolher(pasta: Path, agora: float, dias: int = DIAS) -> list[Path]:
    """Entries of `pasta` (normally /tmp) with nothing touched for `dias` days, except POUPAR and sockets/devices."""
    corte = agora - dias * 86400
    saida = []
    try:
        itens = list(pasta.iterdir())
    except OSError:
        return []
    for item in itens:
        if item.name in POUPAR or item.name.startswith(".X"):
            continue
        try:
            modo = item.lstat().st_mode
        except OSError:
            continue
        import stat
        if not (stat.S_ISDIR(modo) or stat.S_ISREG(modo) or stat.S_ISLNK(modo)):
            continue
        if mais_novo(item) < corte:
            saida.append(item)
    return saida


def tamanho(caminho: Path) -> int:
    if caminho.is_file() or caminho.is_symlink():
        try:
            return caminho.lstat().st_size
        except OSError:
            return 0
    total = 0
    for raiz, _, arquivos in os.walk(caminho):
        for nome in arquivos:
            try:
                total += os.lstat(os.path.join(raiz, nome)).st_size
            except OSError:
                pass
    return total


def apagar(caminho: Path) -> None:
    if caminho.is_dir() and not caminho.is_symlink():
        shutil.rmtree(caminho, ignore_errors=True)
    else:
        try:
            caminho.unlink()
        except OSError:
            pass


def limpar(agora: float | None = None, tmp: Path = TMP, caches: list[Path] | None = None) -> dict:
    """Removes the old /tmp entries and empties the caches. Returns what went and how many bytes."""
    agora = time.time() if agora is None else agora
    feitos, liberado = [], 0
    for item in escolher(tmp, agora):
        liberado += tamanho(item)
        apagar(item)
        feitos.append(str(item))
    for cache in CACHES if caches is None else caches:
        if cache.exists():
            liberado += tamanho(cache)
            apagar(cache)
            feitos.append(str(cache))
    return {"apagados": feitos, "liberado_mb": round(liberado / 1e6)}
