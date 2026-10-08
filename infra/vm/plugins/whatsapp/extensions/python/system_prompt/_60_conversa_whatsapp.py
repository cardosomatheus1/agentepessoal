"""In a chat that comes from WhatsApp, answer the way a phone chat reads well."""

from agent import LoopData
from helpers.extension import Extension

REGRAS = """## Esta conversa é pelo celular (WhatsApp/Telegram)
O usuário está falando com você por mensagem no celular (mensagens com 🎤 são áudios transcritos — pode haver erros de transcrição; se algo parecer estranho, pergunte). Suas respostas finais chegam lá sozinhas (WhatsApp ou Telegram, o que ele usa):
- pergunta simples ou conversa: responda direto, sem usar ferramentas antes (ele está esperando no celular);
- seja curto e direto, como numa conversa de celular; sem tabelas largas nem blocos de código longos;
- use listas curtas e *negrito* só no essencial;
- para mandar arquivo, print ou foto use `whatsapp_enviar`;
- se ele pedir atualizações durante uma tarefa longa (ex.: "me atualize a cada 2 min"), mande cada uma com `notify_user` (chega no celular) e continue trabalhando; confira a hora (`date`) para respeitar o intervalo;
- "/nova" no WhatsApp começa outra conversa; o usuário também vê esta conversa no app."""


class ConversaWhatsapp(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if self.agent and self.agent.number == 0 and self.agent.context.get_data("whatsapp_de"):
            system_prompt.append(REGRAS)
