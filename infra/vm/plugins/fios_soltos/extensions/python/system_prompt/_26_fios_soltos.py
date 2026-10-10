"""Put the person's open loose ends and an index of their other recent chats in every turn, so the agent
links subjects ("isso se liga com...") and notices what was left behind, like Dots."""

import importlib.util
import sys
import time
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

_cache: dict = {}


def _fios():
    nome = "fios_soltos_helper"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "fios.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _indice(f, login: str, atual: str) -> list[str]:
    # parsing every recent chat.json each turn would be slow (some are MBs): refresh every 3 min
    chave = login
    if chave not in _cache or time.time() - _cache[chave][0] > 180:
        _cache[chave] = (time.time(), f.conversas(login, 72))
    linhas = []
    for c in _cache[chave][1]:
        if c["id"] == atual:
            continue
        resumo = c["ultima_resposta"] or (c["pedidos"][-1] if c["pedidos"] else "")
        linhas.append(f"- {c['nome']} (há {c['mudou_ha_h']} h): {f._curto(resumo, 140)}")
        if len(linhas) >= 8:
            break
    return linhas


class FiosSoltosPrompt(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        sep = sys.modules.get("login_usuarios_separacao")
        login = (sep.dono_contexto(self.agent.context) if sep else (self.agent.context.get_data("dono") or "matheus")) or "matheus"
        try:
            f = _fios()
            abertos = f.abertos(login, 6)
            fechados = f.resolvidos_recentes(login)
            indice = _indice(f, login, self.agent.context.id)
        except Exception:
            return
        partes = ["## Fios soltos e ligações",
                  "Você acompanha a vida da pessoa como um todo, não só esta conversa. Use o que está abaixo para:",
                  "- ligar assuntos: se o pedido atual tem relação com um fio solto ou com outra conversa, diga em uma linha "
                  "(\"Isso se liga com …\") e aproveite o que já se sabe em vez de perguntar de novo;",
                  "- notar o esquecido: ao responder, se um fio de prioridade alta ou com prazo perto tiver a ver com o momento, "
                  "lembre em uma linha no fim (sem repetir o mesmo lembrete na mesma conversa);",
                  "- manter o registro com a ferramenta `fios`: \"me lembra\", \"depois eu vejo\", \"preciso fazer\", ou algo que "
                  "você prometeu e não terminou aqui → salvar; algo que você concluiu e fecha um fio → resolver."]
        if abertos:
            partes.append("Fios em aberto (do mais importante):\n" + "\n".join("- " + f.linha(x) for x in abertos))
        if fechados:
            partes.append("Já resolvidos ou dispensados nos últimos 7 dias — não avise de novo sobre o mesmo assunto "
                          "(um e-mail ou alerta repetido sobre isso não é novidade):\n"
                          + "\n".join(f"- {x.get('titulo', '')} ({x.get('estado')})" for x in fechados))
        if indice:
            partes.append("Outras conversas recentes desta pessoa:\n" + "\n".join(indice))
        system_prompt.append("\n".join(partes))
