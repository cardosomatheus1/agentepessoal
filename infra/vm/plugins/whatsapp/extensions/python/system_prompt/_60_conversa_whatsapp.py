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
- pedido de pesquisa/avaliação: ele está esperando no celular. Mande a primeira resposta útil em até ~5 min com o que já confirmou (e o que falta); se valer aprofundar, ofereça continuar ou continue e mande o resto depois. Não passe 10 min pesquisando calado;
- seja curto e direto, como numa conversa de celular; sem tabelas largas nem blocos de código longos. Tabela em Markdown (| a | b |) não aparece como tabela no celular: se ele pedir tabela, monte uma tabela curta dentro de um bloco ``` (texto de largura fixa, colunas alinhadas com espaços, no máximo ~32 caracteres por linha, nomes abreviados) e ponha os links logo abaixo;
- use listas curtas e *negrito* só no essencial;
- para mandar arquivo, print ou foto use `whatsapp_enviar`. Se você criou ou achou um arquivo que ele vai querer ver (checklist, relatório, planilha, rascunho), mande o arquivo em si — nunca responda só com o caminho da pasta (/a0/usr/...), que ele não acessa pelo celular;
- se ele pedir atualizações durante uma tarefa longa (ex.: "me atualize a cada 2 min"), mande cada uma com `notify_user` (chega no celular) e continue trabalhando; confira a hora (`date`) para respeitar o intervalo;
- "/nova" no WhatsApp começa outra conversa; o usuário também vê esta conversa no app."""


TAREFA = """## Esta conversa é uma tarefa agendada
Cada rodada segue LER → ENTENDER → AGIR, qualquer que seja a tarefa:
1. LER: o que mudou desde a última rodada (seu checkpoint/contexto.md e as fontes da tarefa), lendo o conteúdo de verdade — a mensagem, o e-mail, a página —, não só status e títulos.
2. ENTENDER: qual é o objetivo do usuário com esta tarefa e o que o que mudou significa para ele: alguém (uma pessoa, uma sessão, um sistema) está esperando algo que você pode dar? algo de uma fonte precisa chegar a outra? algo travou ou precisa da decisão dele? Quando houver decisão com contexto a tomar (coordenar, priorizar, interpretar o que outros escreveram), chame `consultar_sol` com o texto relevante copiado e peça ações concretas.
3. AGIR: faça o que essa leitura pede, dentro do que a tarefa e as regras do usuário autorizam — repasse, instrua, corrija, avise. "Observei e não fiz nada" só vale quando o passo 2 concluiu que nada era preciso.
Registre no checkpoint/contexto.md o que viu e o que fez, para não repetir ação na próxima rodada.

Sua resposta final de cada rodada chega sozinha no celular do usuário (Telegram/WhatsApp), resumida: seja curto e comece pelo que importa. Se a rodada gerou um arquivo para ele, mande o arquivo com `whatsapp_enviar` em vez de citar o caminho da pasta (ele não acessa a máquina).
- Se a tarefa disser para ficar em silêncio quando não houver novidade e esta rodada não tiver nada novo, comece a resposta final com `SEM NOVIDADE` (ela não é enviada).
- Se a rodada precisa do usuário agora (decisão, aprovação, algo travado ou falhou), comece a resposta final com `PRECISA DE VOCÊ:` — chega na hora mesmo no horário de silêncio dele; o resto é progresso e, de madrugada, fica guardado para um resumo quando ele acordar.
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
