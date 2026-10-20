"""One-time move of Matheus's old stores into the Pasta (20/10, ADR 0001): the decisions (memoria/decisoes), the loose
ends (fios: they become Pendências) and the ficha (it becomes Contexto/perfil.md). Run by the operator
(infra/operador/cerebro.py migrar). The originals stay where they were, read-only, with a copy in
Arquivo-morto/registros-antigos/; from the marker on, the helpers write only to the Pasta. Refuses to run twice."""

import importlib.util
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

USR = Path("/a0/usr")
ANTIGOS = {"decisoes": USR / "memoria" / "decisoes" / "matheus.json", "fios": USR / "fios" / "matheus.json",
           "ficha": USR / "memoria" / "usuarios" / "matheus.md"}
AREAS = (  # first match wins; words of the item's text (accents ignored)
    ("raiz", ("raiz", "prospec", "instagram", "lead", "ifood", "cardapio", "restaurante", "cmv", "erp", "lucro-na-mao")),
    ("nexos", ("nexos", "ia-business", "revenue-os")),
    ("orbyte", ("orbyte",)),
    ("agente", ("agente", "telegram", "whatsapp", "hermes", "openclaw", "codigo", "deploy", "aws", "vm", "drive",
                "google", "rotina", "segundo-cerebro")),
    ("pessoal", ("mei", "pessoal", "saude", "familia", "carreira", "imposto", "banco")),
)


def pasta():
    nome = "cerebro_pasta"
    caminho = Path(__file__).resolve().parent / "pasta.py"
    antigo = sys.modules.get(nome)
    if antigo is None or getattr(antigo, "_mtime", None) != caminho.stat().st_mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = caminho.stat().st_mtime
        if antigo is not None and hasattr(antigo, "RAIZ"):
            modulo.RAIZ = antigo.RAIZ
        sys.modules[nome] = modulo
    return sys.modules[nome]


def area_de(*textos) -> str:
    alvo = pasta().slug(" ".join(str(t or "") for t in textos), 10 ** 5)
    for area, palavras in AREAS:
        if any(re.search(rf"(^|-){re.escape(p)}", alvo) for p in palavras):
            return area
    return "geral"


def _json(caminho: Path) -> dict:
    if not caminho.exists():
        return {}
    d = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(d, dict):
        raise ValueError(f"{caminho.name} não é um objeto JSON")
    return d


def migrar(por: str, simular: bool = False, antigos: dict | None = None) -> dict:
    """{decisoes, pendencias, ficha, simulado}. Raises RuntimeError when already migrated or a source is unreadable."""
    p = pasta()
    antigos = antigos or ANTIGOS
    if (p.RAIZ / p.MARCA_MIGRADO).exists():
        raise RuntimeError("a Pasta já foi migrada; nada foi feito")
    if not str(por or "").startswith("operador:"):
        raise RuntimeError("quem migra é o operador: por='operador: <motivo>'")
    decisoes = _json(antigos["decisoes"]).get("decisoes", [])
    fios = _json(antigos["fios"])
    pendencias = fios.pop("fios", [])
    for x in decisoes:
        x.setdefault("area", area_de(x.get("tema"), x.get("valor")))
    for f in pendencias:
        f.setdefault("area", area_de(f.get("titulo"), f.get("detalhe"), f.get("ligacoes")))
    ficha = antigos["ficha"].read_text(encoding="utf-8") if antigos["ficha"].exists() else ""
    entradas = [l[2:].strip() for l in ficha.splitlines() if l.startswith("- ") and l[2:].strip()]
    resumo = {"decisoes": len(decisoes), "pendencias": len(pendencias), "ficha": len(entradas), "simulado": simular,
              "areas": sorted({x["area"] for x in decisoes + pendencias})}
    if simular:
        return resumo
    p.estrutura()
    p.gravar("decisoes", decisoes)
    p.gravar("pendencias", pendencias)
    p.escrever(p.RAIZ / "Pendencias" / ".meta.json", json.dumps(fios, ensure_ascii=False, indent=1))
    marca_ficha = "Mantida pela ferramenta `ficha`"
    p.escrever(p.RAIZ / "Contexto" / "perfil.md", p.frontmatter({"status": "validado", "tags": ["contexto", "perfil"]})
               + "# Sobre matheus\n\n> " + marca_ficha + " (add, patch, remove), uma entrada por linha, até 4000 "
               "caracteres. Não edite à mão.\n\n" + "".join(f"- {e}\n" for e in entradas))
    copia = p.RAIZ / "Arquivo-morto" / "registros-antigos"
    copia.mkdir(parents=True, exist_ok=True)
    for nome, origem in antigos.items():
        if origem.exists():
            shutil.copy2(origem, copia / f"{nome}-{origem.name}")
            os.chmod(origem, 0o444)
    p.escrever(p.RAIZ / p.MARCA_MIGRADO, json.dumps({"em": time.time(), "por": por, **resumo}, ensure_ascii=False))
    p.versionar(f"migração dos registros antigos ({por})")
    return resumo
