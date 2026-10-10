# auxiliar

O agente como auxiliar pessoal: deixa pronto, lembra na hora certa e acompanha o que depende de outros — sempre
pelo celular, com botões, e nunca enviando, pagando ou respondendo nada por conta própria.

| Ideia | Como funciona |
|---|---|
| **Respostas de e-mail rascunhadas** | O Radar e o vigia do Google acham e-mails que pedem resposta; o agente escreve a resposta no seu estilo e manda com `rascunho` → "✉️ Resposta pronta" com **✅ Usar** (o texto num bloco que copia com um toque; com `gmail:drafts` liberado, vira rascunho no Gmail), **✏️ Ajustar** (ele pergunta o que mudar e manda outra versão) e **🙈 Deixa**. O mesmo e-mail nunca chega duas vezes (`ja_tratado`, 7 dias). |
| **Seu estilo** | Rodada "✍️ Meu estilo de escrita" (dia 1, 10:13): e-mails enviados + o que você digitou no celular (`rascunho amostras` — prompts de tarefas e testes não contam) → `/a0/usr/auxiliar/estilo/<login>.md`, que entra no prompt de toda conversa. |
| **Briefing e pós-reunião** | `reuniao agendar` cria duas tarefas planejadas (acordam a VM): "📅 Briefing" 30 min antes (quem é quem, o que já rolou, pendências, o que levar) e "📝 Pós-reunião" 10 min depois do fim, perguntando o que ficou combinado; a resposta vira fios com prazo (`pos_registrado`). Horário mudou → reagenda; tarefas antigas são limpas depois de 2 dias. |
| **Acordar por evento** | `vigia_google.gs` roda na conta Google (script.google.com, a cada 10 min): e-mails da caixa principal e mudanças na agenda dos próximos 3 dias vão na hora ao gatilho `google`; "Atualizações" (faturas, avisos) no máximo 1×/hora. O gatilho acorda a VM e cai na conversa "Gatilhos" com `gatilho_google.md` como instrução; sem nada a fazer, fica em silêncio. |
| **Esperando de terceiros** | A rodada 🧵 Fios soltos procura e-mails que você mandou há 3–14 dias sem resposta e pedidos parados com outras pessoas; fio com dono "terceiro"; o ✅ Faz pra mim rascunha uma cobrança gentil. |
| **Contas e vencimentos** | `contas salvar` (valor decimal + moeda; a mesma conta não duplica). Os lembretes saem sem chamar modelo (`job_loop/_58`): 3 dias antes, véspera e no dia, das 8h às 21h, com **✅ Já paguei / ⏰ Amanhã / 🙈 Não é minha**. Nunca paga. |
| **Revisão da semana** | Rodada "🗓️ Revisão da semana" (domingo 19:47): o que andou, o que travou, a semana que vem, padrões que podem virar rotina e 1 foco. |
| **Resumo da manhã em áudio** | Quando a rodada "📰 Resumo do dia" termina, o Luna reescreve para ouvir (~1 min) e a Polly (Camila) gera a nota de voz pelo proxy da VM (`/arquivos/voz`; o contêiner não tem credenciais AWS); chega como mensagem de voz no Telegram. |

Registro: `/a0/usr/auxiliar/<login>.json` (rascunhos, contas, reuniões). Botões: `rd:` e `ct:` em
`plugins/whatsapp/api/receber.py`.
