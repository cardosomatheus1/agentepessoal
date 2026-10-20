"""Give the agent the person's writing style, bills coming due and meetings waiting for a "how did it go?" answer."""

import importlib.util
import sys
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension


def aux():
    nome = "auxiliar_helper"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "auxiliar.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


class AuxiliarPrompt(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        sep = sys.modules.get("login_usuarios_separacao")
        login = (sep.dono_contexto(self.agent.context) if sep else (self.agent.context.get_data("dono") or "matheus")) or "matheus"
        try:
            a = aux()
            perfil = a.estilo(login)
            contas = a.contas_abertas(login, 7)
            pos = a.pos_pendentes(login)
        except Exception:
            return
        partes = ["## Auxiliar pessoal",
                  "- E-mail que pede resposta da pessoa → escreva a resposta e entregue com `rascunho` (quem envia é a pessoa; você nunca envia).",
                  "- Conta, boleto, fatura ou renovação com data → `contas` salvar. Reunião de verdade na agenda → `reuniao` agendar."]
        ctx = self.agent.context
        if perfil and not ctx.get_data("_estilo_escrita"):
            pedido = getattr(getattr(loop_data, "user_message", None), "content", "")
            if a.quer_estilo(pedido):
                ctx.set_data("_estilo_escrita", True)  # sticky for the chat: the prompt prefix stays stable (cache)
        if perfil and ctx.get_data("_estilo_escrita"):
            partes.append("Estilo de escrita da pessoa (siga ao escrever qualquer coisa em nome dela):\n" + perfil[:2500])
        elif perfil:
            partes.append("- Antes de escrever algo em nome da pessoa (e-mail, mensagem, post), leia o estilo dela com "
                          "`rascunho` acao \"estilo\".")
        if contas:
            partes.append("Contas abertas vencendo em até 7 dias:\n" + "\n".join(f"- [{c['id']}] {a.linha_conta(c)}" for c in contas))
        for r in pos:
            partes.append(f"Você perguntou como foi a reunião «{r['titulo']}» (evento_id {r['evento_id']}, {r['inicio_txt']}). "
                          "Se a mensagem for sobre isso: crie UM fio por combinado (`fios` salvar: titulo = o que, dono = quem, "
                          "prazo AAAA-MM-DD quando houver data ou dia da semana), sem fios extras (nada de \"reunião realizada\"), "
                          "e confirme em poucas linhas o que vai lembrar. Decisão que ele tomou na reunião vai na `decisao`; "
                          "no fim, `reuniao` pos_registrado com `resumo` (2–3 linhas) e `decisoes` (\"decisao:N\") completa "
                          "a nota da reunião no Segundo Cérebro.")
        system_prompt.append("\n".join(partes))
