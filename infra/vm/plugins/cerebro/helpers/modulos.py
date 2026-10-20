"""Load this plugin's helpers (and the few of other plugins it writes through) by path, reloaded when a file changes;
pasta.RAIZ keeps a value a test or the operator set."""

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# next to this plugin (repository, live install); a staging copy alone in /tmp uses the installed ones
PLUGINS = RAIZ.parent if (RAIZ.parent / "memoria_pessoal").exists() else Path("/a0/usr/plugins")
CAMINHOS = {
    "pasta": ("cerebro_pasta", RAIZ / "helpers" / "pasta.py"),
    "assuntos": ("cerebro_assuntos", RAIZ / "helpers" / "assuntos.py"),
    "reunioes": ("cerebro_reunioes", RAIZ / "helpers" / "reunioes.py"),
    "captura": ("cerebro_captura", RAIZ / "helpers" / "captura.py"),
    "dia": ("cerebro_dia", RAIZ / "helpers" / "dia.py"),
    "auditoria": ("cerebro_auditoria", RAIZ / "helpers" / "auditoria.py"),
    "migracao": ("cerebro_migracao", RAIZ / "helpers" / "migracao.py"),
    "raiz": ("cerebro_raiz", RAIZ / "helpers" / "raiz.py"),
    "decisoes": ("memoria_pessoal_decisoes", PLUGINS / "memoria_pessoal" / "helpers" / "decisoes.py"),
    "conversas": ("memoria_pessoal_conversas", PLUGINS / "memoria_pessoal" / "helpers" / "conversas.py"),
    "fios": ("fios_soltos_helper", PLUGINS / "fios_soltos" / "helpers" / "fios.py"),
    "ponte": ("whatsapp_ponte", PLUGINS / "whatsapp" / "helpers" / "ponte.py"),
}


def m(qual: str):
    nome, caminho = CAMINHOS[qual]
    antigo = sys.modules.get(nome)
    if qual == "ponte" and antigo is not None:
        return antigo
    if antigo is None or getattr(antigo, "_mtime", None) != caminho.stat().st_mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = caminho.stat().st_mtime
        if antigo is not None and hasattr(antigo, "RAIZ") and qual == "pasta":
            modulo.RAIZ = antigo.RAIZ
        sys.modules[nome] = modulo
    return sys.modules[nome]
