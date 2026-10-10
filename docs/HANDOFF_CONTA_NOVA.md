# Agente pessoal — passagem para a conta nova do Claude

Retrato de 10/10/2026. A conversa antiga do Claude Code não passa para a conta nova: tudo o que importa está neste
repositório (código, este documento e `infra/operador/`) e na própria máquina do agente, que continua igual.

## O que é

O **agente pessoal do Matheus** é um Agent Zero rodando numa EC2 da AWS (conta `964862484412`, `us-east-1`), com
plugins próprios em `infra/vm/plugins/`. Ele fala com o Matheus pelo **Telegram** (e WhatsApp), roda rotinas
agendadas, navega com um navegador próprio por pessoa e usa modelos via Bedrock/OpenAI-compatível.

Nada do agente depende da conta do Claude: ele continua rodando durante e depois da troca.

| Peça | Onde | Observação |
|---|---|---|
| VM do agente | EC2 `i-0498b4f39560b01a9` | Acesso só por SSM (`infra/operador/vmcmd.py`) |
| Agent Zero | contêiner `agent-zero` | Dados em `/opt/a0/usr` (no contêiner, `/a0/usr`) |
| Plugins | `/opt/a0/usr/plugins/<nome>` | Fonte: `infra/vm/plugins/` deste repo |
| Proxy de modelos | `/opt/agentepessoal/bedrock_proxy.py`, serviço `agentepessoal-proxy`, porta 8787 | Luna (`openai.gpt-6-luna`), Haiku 5.5, Polly (voz), token do GCP |
| Ponte do celular | `/opt/agentepessoal/ponte_whatsapp.py`, serviço `agentepessoal-whatsapp`, porta 8789 | Telegram ligado ao login `matheus`; cofre `/senha` |
| Agendador | `/opt/a0/usr/scheduler/tasks.json` | Mexer só pelas APIs `scheduler_task_*` |
| Tarefas permanentes | `/opt/a0/usr/agenda/limites.json` | Senão o `agenda_confiavel` desativa após 30 dias |
| Backups/arquivos temporários | S3 `agentepessoal-backup-964862484412` (`tmp/`) | Usado para levar arquivos para a VM |

## O que a sessão nova precisa ter

1. **GitHub**: a conta nova conectada ao usuário `cardosomatheus1`, com acesso a `cardosomatheus1/agentepessoal`.
2. **Ambiente na nuvem** (claude.ai/code → ambiente → novo), com:
   - variáveis `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION=us-east-1` (a mesma credencial IAM usada
     hoje — o Matheus copia do ambiente antigo ou gera outra no IAM; nunca colar no chat);
   - `A0_SENHA` = senha do login `matheus` na interface do Agent Zero (o Matheus sabe; não vai para o git);
   - credenciais de rede, se quiser as mesmas de hoje: OpenAI, Tavily, TypeSafe (Jev) e Bedrock.
3. Dependências na sessão: `pip install boto3 playwright` (o Chromium já vem no contêiner do Claude Code).

## Como operar (scripts em `infra/operador/`)

| Script | Para quê |
|---|---|
| `vmcmd.py '<comando>'` | Roda um comando na VM do agente por SSM (até ~10 min) |
| `mandar_msg.py <arquivo> [chat]` | Manda uma mensagem ao agente como `matheus` (chat novo se não passar o id) |
| `rodar_testes.py [so\|LIMPAR]` | Suíte do plugin `auxiliar` |
| `rodar_testes_pro.py` | Suíte do plugin `prospeccao` (29 testes) |
| `infra/vm/plugins/prospeccao/rodadas.py [--criar] [buscar\|executar\|semana\|resumo]` | Cria/atualiza/dispara as rodadas da prospecção |
| `tarefas_auxiliar.py`, `resumo_novo.py` | Tarefas do auxiliar e do resumo diário |
| `resetar_chat.py <ctx>`, `apagar_chat.py` | Limpar conversas de teste |
| `ver_chat.sh <ctx>` (rodar na VM) | Últimas mensagens de uma conversa do agente |

**Implantar um plugin**: `tar czf pro.tgz -C infra/vm/plugins <plugin>` → `aws s3 cp` para `tmp/` do bucket →
`vmcmd.py` copiando para `/opt/a0/usr/plugins/` → `docker exec agent-zero curl -s -X POST http://127.0.0.1:80/api/cache_reset`.
Serviços do host (`bedrock_proxy.py`, `ponte_whatsapp.py`): `install -m 755` em `/opt/agentepessoal/` e
`systemctl restart agentepessoal-proxy|agentepessoal-whatsapp`.

**Mandar algo ao Telegram do Matheus** (na VM): carregar `/a0/usr/plugins/whatsapp/helpers/ponte.py` e chamar
`enviar("matheus", texto, tipo="resposta"|"urgente"|"progresso")`. Logins `teste_*` só gravam em
`/a0/usr/testes/celular.jsonl`.

## Rotinas agendadas do agente (10/10)

| Id | Nome | Quando (America/Bahia) |
|---|---|---|
| nW924Nkj | 📰 Resumo do dia | 7:45 |
| HL76nfIg | 🔎 Radar (Gmail e Agenda) | 8:40, 11:40, 14:40, 17:40, 20:40 |
| 8COQyGTD | 🧵 Fios soltos | 9:10, 13:10, 18:10 |
| 2FIQTI0o | 💡 Iniciativa | 9:37 a 19:37, de 2 em 2 h |
| bMU33E1T | 🗓️ Revisão da semana | domingo 19:47 |
| INZXd4Gi | ✍️ Meu estilo de escrita | dia 1, 10:13 |
| lu1v3ube | Radar diário de IA (YouTube) | 5:00 |
| laMIuaPt | 🎯 Prospecção — buscar | 9:23, todo dia |
| F9Ku9frw | 🎯 Prospecção — executar | :20 e :50, 9h–19h, todo dia |
| aPzaUZiW | 🎯 Prospecção — resumo do dia | 20:17 |
| gOqdMBE3 | 🎯 Prospecção — semana | segunda 8:41 |
| H8kWmYP1 | Nexos — acompanhar fase 2 e lead | 0, 6, 12, 18 h |
| 2FQESGed | Acompanhar Claude Code — MVP | de hora em hora — **dependia do login antigo do claude.ai no navegador do agente**; o navegador agora está na conta `sejaorbyte@gmail.com` |

## Frentes de trabalho e onde pararam

- **Iniciativa** (`iniciativa`): mensagens proativas com revisor Luna; arquivos vão anexados (md → PDF).
- **Auxiliar** (`auxiliar`): rascunhos de e-mail no estilo do Matheus, briefing antes e pergunta depois de reunião,
  vigia do Google por Apps Script (**o Matheus ainda precisa instalar o `vigia_google.gs`**), esperando terceiros,
  contas com lembrete, revisão semanal, resumo da manhã em áudio (Polly Camila generative, só generative).
- **Cofre** (`cofre`): senhas com descrição de uso; o agente usa direto e só para em captcha, 2FA ou senha errada.
- **Prospecção Raiz Connect** (`prospeccao`) — a frente mais ativa:
  - conta **@raiz.connect** (nunca a pessoal @cardosomatheus1); limites do piloto 8 aquecer / 5 DMs / 5 lembretes
    por dia na 1ª semana, depois 20/12/10;
  - nota do lead 0–100 calculada pelo código a partir das evidências (corte 55);
  - aquecer, 1ª mensagem e lembrete **pré-aprovados pelo Matheus** dentro dos limites, cada texto passa por um
    revisor Luna (bateria `tests/bateria_revisor.py`: 30/30); respostas e parceiros continuam com o ✅ dele;
  - 1ª mensagem: variante A = pergunta sobre como precifica (sem oferta, sem link); B = oferta do cálculo grátis;
  - links permitidos só no lembrete e nas respostas: calculadora
    `raizconnect.com.br/materiais/precificacao/calculadora` e simulador `.../materiais/quanto-sobra-no-delivery`;
  - cada rodada de execução lê o Direct e as notificações e registra (`conferido`) antes de executar; resposta em
    comentário ou no Direct avisa o Matheus no Telegram na hora (uma vez por resposta);
  - estado de 10/10: 9 leads (Salvador), 8 aquecidos, @zen.marmitas aprovado na fila; primeiras DMs na segunda 12/10;
    ninguém respondeu ainda.
- **Faturamento Vertex/Gemini**: liberado (R$ 0 de saldo devedor, orçamento de R$ 50).
- **Análise dos anúncios da Raiz** (só leitura): iscas com muito LPV e pouco cadastro; sugestões no histórico
  (calculadora como destino dos anúncios; Raio-X e 15 erros marcam "às vezes" como erro inteiro).

## Regras que o Matheus deu (valem sempre)

- Segredos só no cofre/SSM; nunca no chat, em arquivo ou no git. Nunca repetir senha ou token.
- Nada de pagamento, campanha com gasto ou meio de pagamento; contas de anúncio reais e o app Barber Dock: só leitura.
- Mensagem a terceiros só com aprovação (exceto a prospecção pré-aprovada, dentro dos limites).
- Não resolver nem contornar captcha; o Matheus resolve pela tela do navegador do agente.
- Sem identificador de modelo em commits; push só no branch de trabalho; PR só se ele pedir.
- Respostas a ele em português, curtas e objetivas; avisos só do que importa.

## Prompt para a primeira mensagem da sessão nova

```
Você continua o projeto do agente pessoal do Matheus (repo cardosomatheus1/agentepessoal), vindo de outra conta do
Claude. Leia docs/HANDOFF_CONTA_NOVA.md inteiro antes de qualquer coisa e siga as regras dele. Confira o acesso:
aws sts get-caller-identity; python3 infra/operador/vmcmd.py 'docker ps --format "{{.Names}} {{.Status}}"'.
Depois rode python3 infra/operador/rodar_testes_pro.py e me diga em 3 linhas o estado (VM, testes, prospecção).
Responda sempre em português, curto.
```
