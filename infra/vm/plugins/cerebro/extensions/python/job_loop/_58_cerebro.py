"""The Segundo Cérebro's clock (20/10): at 20h (Bahia) the nota do dia (helpers/dia.py) with a 3-line summary to
Matheus's phone and, while the context interview is unfinished, an invitation for the next section; a version of the
Pasta every hour (git: its history); the audit (helpers/auditoria.py) once a month."""

import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_ULTIMO = {"checado": 0.0, "versao": 0.0}
HORA_COPIA = 3  # the daily copy to GitHub (Q20), at night


def mods():
    nome, caminho = "cerebro_modulos", RAIZ / "helpers" / "modulos.py"
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]


def token() -> str:
    """The GitHub token of the vault (cofre plugin), read only for the push."""
    try:
        caminho = RAIZ.parent / "cofre" / "helpers" / "cofre.py"
        spec = importlib.util.spec_from_file_location("cofre_para_cerebro", caminho)
        c = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(c)
        return str(c.carregar("matheus").get("GITHUB_TOKEN") or "")
    except Exception:
        return ""


def tique(agora: float | None = None, enviar=None) -> list:
    """What this tick did (for the log and the tests)."""
    agora = agora or time.time()
    m = mods()
    p = m.m("pasta")
    if not p.ativa(p.DONO):
        return []
    enviar = enviar or (lambda texto: m.m("ponte").enviar(p.DONO, texto))
    feito = []
    dia = m.m("dia")
    if dia.hora_de_escrever(p, agora):
        nota = dia.escrever(p, agora)
        convite = dia.convite_entrevista(p)
        enviar(nota["resumo"] + (f"\n\n{convite}" if convite else ""))
        feito.append(f"nota do dia {nota['data']}")
    if agora - _ULTIMO["versao"] > 3600:
        _ULTIMO["versao"] = agora
        if p.versionar("versão da hora"):
            feito.append("versão")
    t = p.agora_local(agora)
    marca_copia = p.RAIZ / ".copia-github"
    if t.tm_hour >= HORA_COPIA and (not marca_copia.exists() or marca_copia.read_text().strip() != p.data(agora)):
        erro = p.enviar_copia(token())
        p.escrever(marca_copia, p.data(agora))
        feito.append("cópia no GitHub" if not erro else f"cópia no GitHub falhou: {erro}")
    auditorias = list((p.RAIZ / "Documentos").glob(f"auditoria-{time.strftime('%Y-%m', t)}-*.md"))
    if t.tm_mday == 1 and t.tm_hour >= 20 and not auditorias:
        r = m.m("auditoria").gravar(p, agora)
        enviar(f"🔎 Auditoria mensal do Segundo Cérebro: {r['nota']}/100, {len(r['achados'])} ponto(s) para arrumar.")
        feito.append(f"auditoria {r['nota']}")
    return feito


class CerebroRelogio(Extension):
    async def execute(self, **kwargs):
        agora = time.time()
        if agora - _ULTIMO["checado"] < 60:
            return
        _ULTIMO["checado"] = agora
        try:
            feito = tique(agora)
            if feito:
                print(f"cerebro: {', '.join(feito)}", flush=True)
        except Exception as exc:
            print(f"cerebro: relógio falhou: {type(exc).__name__}: {exc}", flush=True)
