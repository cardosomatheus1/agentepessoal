"""The Segundo Cérebro in every turn of Matheus's chats (20/10): how it works (the Pasta, automatic anotação, how to
answer questions from it, the interview) in the system prompt, and the open Assuntos with where they stopped at the
end of the turn (they change; the system prompt stays cache-stable)."""

import importlib.util
import sys
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def mods():
    nome, caminho = "cerebro_modulos", RAIZ / "helpers" / "modulos.py"
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        sys.modules[nome] = modulo
    return sys.modules[nome]


REGRAS = """## Segundo Cérebro
O Segundo Cérebro do Matheus é a Pasta (/a0/usr/segundo_cerebro/pasta): Contexto/, Raiz/, Decisoes/, Pendencias/, Assuntos/,
Reunioes/, Notas-do-dia/, Projetos/, Documentos/. É a única fonte do que ele decidiu, discute e deixou por fazer.
- Anotação: depois de cada mensagem dele no celular, a anotação automática registra sozinha Decisões, Pendências e
  Assuntos e manda uma linha "📌 Anotei …". Você não precisa repetir. Se ele corrigir ("era só ideia", "tira isso",
  "não era decisão"), desfaça com `cerebro` acao=desfazer (ref ou "ultimo") e registre do jeito certo.
- Pergunta sobre o que ele decidiu, deve fazer, onde parou um assunto, quem é alguém: responda pela Pasta
  (`cerebro` acao=consultar, `decisao` listar, `fios` listar) citando a nota; o que não está lá, diga que não está.
- Pendência = o que ELE precisa fazer. Decisão = escolha feita. Assunto = tema em andamento com onde parou. Toda
  pendência e decisão tem área (raiz, nexos, orbyte, agente, pessoal, geral).
- Reunião que ele conta (com quem, o que decidiu, o que ficou para fazer) → `cerebro` acao=reuniao, uma nota por
  reunião em Reunioes/ ligada às decisões e pendências; a da agenda, depois do pós-reunião, já ganha a nota.
- Raiz (prospecção, posts, oferta, cliente, marca, concorrentes): leia ANTES `cerebro` acao=raiz, o Cérebro da Raiz
  (Raiz/ na Pasta). A oferta se chama Lucro na Mão em 30 Dias. O que vier pendente de validação não é fato.
- Entrevista de contexto: quando ele aceitar ("bora"), faça UMA seção de Contexto por vez (`cerebro` acao=contexto):
  leia o que já existe, pergunte, resuma e só grave depois do ok dele, sem inventar."""


def bloco(m) -> str:
    try:
        a = m.m("assuntos").abertos(8)
        p = m.m("pasta")
        faltam = [p.CONTEXTO[n][0] for n in p.contexto_pendente() if n != "perfil.md"]
    except Exception:
        return ""
    partes = []
    if a:
        partes.append("Assuntos em andamento (onde pararam):\n" + "\n".join("- " + m.m("assuntos").linha(x) for x in a))
    if faltam:
        partes.append("Contexto ainda sem entrevista: " + ", ".join(faltam))
    return "\n".join(partes)


def texto_dele(agent) -> str:
    msg = getattr(agent, "last_user_message", None)
    c = getattr(msg, "content", msg)
    texto = (c.get("user_message") or c.get("message") or "") if isinstance(c, dict) else c
    return str(texto or "")


def relevantes_do_turno(m, agent) -> str:
    try:
        abertos = {f"Assuntos/{a['id']}-" for a in m.m("assuntos").abertos(8)}
        texto = m.m("briefing").relevantes(m, texto_dele(agent))
        # the open fronts already go in "segundo_cerebro": no repeat
        linhas = [l for l in texto.splitlines() if not any(l.startswith(f"- [[{x}") for x in abertos)]
        return "\n".join(linhas) if len(linhas) > 1 else ""
    except Exception:
        return ""


class CerebroPrompt(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        sep = sys.modules.get("login_usuarios_separacao")
        login = (sep.dono_contexto(self.agent.context) if sep else (self.agent.context.get_data("dono") or "matheus")) or "matheus"
        m = mods()
        if not m.m("pasta").ativa(login):
            return
        system_prompt.append(REGRAS)
        memo = getattr(loop_data, "params_persistent", None)
        extras = getattr(loop_data, "extras_persistent", None)
        if isinstance(memo, dict) and isinstance(extras, dict):
            turno = memo.setdefault("_no_turno", {})
            if "segundo_cerebro" not in turno:
                turno["segundo_cerebro"] = bloco(m)
            if turno["segundo_cerebro"]:
                extras["segundo_cerebro"] = turno["segundo_cerebro"]
            # 21/10: the notes that match what he just wrote come with the turn (he should not have to ask the agent
            # to look; local search, no model, once per message)
            if "cerebro_relevante" not in turno:
                turno["cerebro_relevante"] = relevantes_do_turno(m, self.agent)
            if turno["cerebro_relevante"]:
                extras["cerebro_relevante"] = turno["cerebro_relevante"]
