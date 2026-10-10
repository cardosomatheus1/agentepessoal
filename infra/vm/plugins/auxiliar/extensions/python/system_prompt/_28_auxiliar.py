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
                  "- E-mail que pede resposta dele → escreva a resposta e entregue com `rascunho` (ele envia; você nunca envia).",
                  "- Conta, boleto, fatura ou renovação com data → `contas` salvar. Reunião de verdade na agenda → `reuniao` agendar."]
        if perfil:
            partes.append("Estilo de escrita dele (siga ao escrever qualquer coisa em nome dele):\n" + perfil[:2500])
        if contas:
            partes.append("Contas abertas vencendo em até 7 dias:\n" + "\n".join(f"- [{c['id']}] {a.linha_conta(c)}" for c in contas))
        for r in pos:
            partes.append(f"Você perguntou como foi a reunião «{r['titulo']}» (evento_id {r['evento_id']}, {r['inicio_txt']}). "
                          "Se a mensagem dele for sobre isso: transforme o combinado em fios (`fios` salvar: o que, quem, "
                          "prazo), confirme em poucas linhas o que vai lembrar e chame `reuniao` acao \"pos_registrado\".")
        system_prompt.append("\n".join(partes))
