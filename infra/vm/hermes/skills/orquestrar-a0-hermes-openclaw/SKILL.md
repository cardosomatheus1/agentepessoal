---
name: orquestrar-a0-hermes-openclaw
description: "Escolher, para cada tarefa, entre fazer direto ou passar a ajudantes (delegate_task) ou à caixa isolada (terminal_isolado), e conferir o que eles entregam."
version: 1.0.0
adaptada_hermes: 2026-10-23
origem_a0: 1.0.0
tags: ["rotina", "matheus"]
trigger_patterns:
  - "orquestrar"
  - "delegar hermes"
  - "delegar openclaw"
  - "escolher agente"
  - "divisão de tarefas agentes"
  - "fluxograma orquestração"
  - "usar o hermes"
  - "usar o openclaw"
---
# orquestrar-a0-hermes-openclaw

Rotina salva em 20/10/2026 por matheus.

## Quando usar
Use quando o pedido tiver partes de código, dados ou pesquisa na web que valem um executor separado, ou quando o Matheus pedir para usar o Hermes ou o OpenClaw.

## Entradas e acessos
- Pedido do Matheus.
- Arquivos dele nas pastas de trabalho (/a0/usr/workdir, projects, uploads, downloads).
- `delegate_task` para ajudantes em paralelo.
- `terminal_isolado` para rodar coisas numa caixa sem nada do Matheus.

## Passos
1. Separe o pedido em partes e defina o resultado verificável de cada uma.
2. Algumas partes ficam com o agente principal (você), sem delegar:
   - contas e senhas;
   - navegador logado;
   - Gmail, Agenda e Drive;
   - WhatsApp, Telegram e Instagram;
   - mensagens a pessoas;
   - dinheiro;
   - prospecção Raiz (fluxo com playbook, cotas e revisor);
   - agendamentos;
   - o que é curto (delegar custa minutos).
3. Trabalho real pode sair do agente principal de dois jeitos:
   - para ajudantes via `delegate_task`;
   - para a caixa isolada via `terminal_isolado`, quando é código ou arquivo que não precisa de nada do Matheus.

   Os dois têm ferramentas de verdade: terminal, arquivos, internet, navegador, busca, Python com pandas/openpyxl/matplotlib, node e ffmpeg.
4. Escolha o ajudante pela tarefa:
   - **Código e dados** (o antigo papel do Hermes): scripts, planilhas, PDFs, conversões, gráficos, arquivos prontos.
   - **Pesquisa e leitura na web aberta com fontes** (o antigo papel do OpenClaw): trabalho de vários passos e segunda opinião independente.
5. Escreva um brief autossuficiente:
   - objetivo, contexto, critério de pronto e onde salvar o resultado (ex.: /a0/usr/workdir/delegados/<tarefa>/);
   - os caminhos dos arquivos de entrada nas pastas de trabalho;
   - nunca senhas, tokens ou dados pessoais desnecessários.
6. Partes independentes podem ir a ajudantes diferentes ao mesmo tempo no mesmo `delegate_task`. Faça uma retentativa no máximo, com abordagem nova. Se falhar de novo, passe ao outro tipo de ajudante ou faça direto.
7. Confira o que voltou: abra os arquivos (`read_file`, `ler`), refaça as contas por outro caminho e cheque as fontes. A resposta dos ajudantes não vale como verificada até você conferir.

## Como verificar que deu certo
- Cada parte tem resultado conferido pelo agente principal: arquivo aberto, conta refeita, fonte checada.
- Nada que precise de conta, mensagem ou dinheiro saiu do agente principal.

## O que entregar
Resultado integrado e verificado, dizendo quem fez cada parte e onde estão os arquivos.

## Precisa de aprovação do usuário
Delegar não precisa de OK. Continuam precisando de aprovação:
- mensagens a terceiros;
- pagamentos;
- apagar coisas do Matheus;
- termos e acessos novos.

CAPTCHA só o Matheus resolve.
