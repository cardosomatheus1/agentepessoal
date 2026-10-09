"""In a chat that comes from WhatsApp, answer the way a phone chat reads well; in a scheduled
task, know that the final answer goes to the phone (and how to stay quiet)."""

import importlib.util
import sys
from pathlib import Path

from agent import LoopData
from helpers.extension import Extension

REGRAS = """## Esta conversa é pelo celular (WhatsApp/Telegram)
O usuário está falando com você por mensagem no celular (mensagens com 🎤 são áudios transcritos — pode haver erros de transcrição; se algo parecer estranho, pergunte). Suas respostas finais chegam lá sozinhas (WhatsApp ou Telegram, o que ele usa):
- ele escreve abreviado, como no celular: "n" = NÃO, "vc" = você, "td" = tudo, "q" = que, "p"/"pra" = para, "tbm" = também, "pq" = porque, "kd" = cadê, "msg" = mensagem, "qd" = quando. Atenção a "n": "n espera" é "NÃO espere", "n faz" é "NÃO faça". Se uma ordem puder ser lida ao contrário, siga a leitura com "não" ou pergunte antes de esperar/agir;
- pergunta simples ou conversa: responda direto, sem usar ferramentas antes (ele está esperando no celular);
- seja curto e direto, como numa conversa de celular; sem tabelas largas nem blocos de código longos;
- use listas curtas e *negrito* só no essencial;
- para mandar arquivo, print ou foto use `whatsapp_enviar`;
- se ele pedir atualizações durante uma tarefa longa (ex.: "me atualize a cada 2 min"), mande cada uma com `notify_user` (chega no celular) e continue trabalhando; confira a hora (`date`) para respeitar o intervalo;
- "/nova" no WhatsApp começa outra conversa; o usuário também vê esta conversa no app."""


TAREFA = """## Esta conversa é uma tarefa agendada
Sua resposta final de cada rodada chega sozinha no celular do usuário (Telegram/WhatsApp), resumida: seja curto e comece pelo que importa.
- Se a tarefa disser para ficar em silêncio quando não houver novidade e esta rodada não tiver nada novo, comece a resposta final com `SEM NOVIDADE` (ela não é enviada).
- Termine cada rodada com a resposta final; não fique esperando a próxima rodada dentro desta."""


def ponte():
    nome = "whatsapp_ponte"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "ponte.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        for estado in ("PENDENTES", "PEDIDOS"):
            if antigo is not None and hasattr(antigo, estado):
                setattr(modulo, estado, getattr(antigo, estado))
        sys.modules[nome] = modulo
    return sys.modules[nome]


class ConversaWhatsapp(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent or self.agent.number != 0:
            return
        if self.agent.context.get_data("whatsapp_de"):
            system_prompt.append(REGRAS)
        elif ponte().tarefa(self.agent.context):
            system_prompt.append(TAREFA)
