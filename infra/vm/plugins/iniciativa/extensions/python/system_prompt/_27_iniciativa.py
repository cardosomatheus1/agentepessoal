"""Tell the agent what it recently sent on its own initiative (so a reply like "faz isso" or "não curti" makes
sense in any chat) and to record what the person says about those messages as a learning."""

import importlib.util
import sys
import time
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension


def _ini():
    nome = "iniciativa_helper"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "iniciativa.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


class IniciativaPrompt(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        sep = sys.modules.get("login_usuarios_separacao")
        login = (sep.dono_contexto(self.agent.context) if sep else (self.agent.context.get_data("dono") or "matheus")) or "matheus"
        try:
            d = _ini().carregar(login)
        except Exception:
            return
        recentes = [e for e in d["enviadas"] if time.time() - e["quando"] < 2 * 86400][-3:]
        partes = ["## Iniciativa própria",
                  "Às vezes você manda mensagens por conta própria (💡) ao celular da pessoa. Quando ela comentar sobre "
                  "uma delas ou sobre o que quer receber assim (\"gostei\", \"não me manda isso\", \"mais disso\"), "
                  "registre com `iniciativa` acao \"aprender\" numa frase objetiva."]
        if recentes:
            partes.append("Suas últimas mensagens por iniciativa (se a pessoa responder sobre elas, é disso que fala):\n"
                          + "\n".join(f"- {time.strftime('%d/%m %H:%M', time.localtime(e['quando']))}: {e['titulo']} — "
                                      f"{e['texto'][:160]}" for e in recentes))
        system_prompt.append("\n".join(partes))
