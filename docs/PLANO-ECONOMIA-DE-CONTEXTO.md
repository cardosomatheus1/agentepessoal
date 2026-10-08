# Plano: economizar contexto (e custo) do agente

Status: **em execução** (08/10/2026).

## Resultado até agora

| Etapa | Feito | Medido |
|---|---|---|
| Medição | o proxy grava `entrada`, `cache`, `cache_gravado` e `saida` de cada chamada em `/var/lib/agentepessoal/uso.jsonl` | linha de base: ~78 mil tokens por passo na conversa da Meta, **0% de cache** |
| Alavancas 1, 3 e 7 | `ctx_history` 0.25; página do navegador ≤ 20 mil caracteres; 3 memórias e 1 solução lembradas; não reler o `contexto.md` | passo na conversa da Meta: ~78 mil → ~44–56 mil tokens |
| Alavanca 5 (cache) | plugin `cache_prompt`: extras no histórico só com o que mudou, sem bloco no fim (o cache do Bedrock só aproveita quando o prompt novo começa com o anterior inteiro) | mesma tarefa: 0% → **79%** da entrada em cache, custo **−55%**, mesmo acerto |
| Alavanca 2 | plugin `resultados_grandes`: resultado de ferramenta acima de 8 mil caracteres vai para `chats/<id>/saidas/`; no histórico ficam começo, fim e caminho | no teste, um resultado do navegador de 72 mil caracteres ficou com ~6,5 mil no histórico; **83%** em cache, ~US$ 0,0015 por passo (sem as mudanças: ~US$ 0,0038) |
| Alavanca 6 | regra: tarefa nova e independente → `call_subordinate` com `reset: true`; navegação longa em subagente limpo | — |
| Alavanca 4 | **não feita**: com o cache, instruções e definições de ferramentas (~17 mil tokens fixos) já saem a 1/10 do preço; o ganho não compensa o risco de o agente usar mal as ferramentas | — |

## O problema, medido

Tarefa da Meta (07/10, 16h30–19h30): **835 chamadas ao Sol, 67,3 milhões de tokens de entrada e só
231 mil de saída** — ~80 mil tokens por chamada. O custo está quase todo em **reler a conversa**, não
em responder.

Última chamada do agente principal (conversa `H91mXoKi`), ~99 mil tokens:

| Parte | Tamanho | % | O que tem |
|---|---|---|---|
| Instruções fixas (system) | 58 mil caracteres | ~18% | manuais das ferramentas (~30 mil), skills, memória pessoal, `contexto.md` da conversa |
| Mensagens "Human" (resultados de ferramentas + mensagens) | 220 mil caracteres | ~68% | 121 mensagens: imagem do `vision_load` (21 mil), resultado de subagente (15 mil), leituras do `contexto.md` (9 mil + 8,5 mil), páginas do navegador |
| Respostas do agente | 45 mil caracteres | ~14% | 120 passos (pensamentos + chamadas) |

Por que cresce tanto: o preset usa `ctx_length: 200000` e `ctx_history: 0.7`, ou seja, o histórico só é
resumido depois de **~140 mil tokens**. Até lá, cada passo reenvia tudo.

Outras descobertas:
- O `contexto.md` já entra nas instruções a cada passo **e** o agente ainda o lê/edita com
  `text_editor`, que devolve o arquivo inteiro — o mesmo texto aparece 2–3 vezes.
- Imagens do `vision_load` ficam no histórico até serem expulsas pelo limite de 30.
- O CloudWatch não mostra quanto do prompt veio do cache; hoje não sabemos a taxa de acerto.

## Alavancas (da maior para a menor)

### 1. Orçamento de histórico menor — economia estimada 35–50%
- Baixar `ctx_history` para que o histórico seja resumido por volta de **35–40 mil tokens**
  (ex.: `ctx_history: 0.2` com `ctx_length: 200000`), em vez de 140 mil.
- Custo: mais chamadas de resumo (feitas pelo Luna, barato) e risco de perder detalhe — coberto pelas
  alavancas 2 e 3.
- Teste: repetir uma tarefa típica e comparar tokens e se o agente "esquece" algo.

### 2. Resultados grandes vão para arquivo — economia estimada 15–25%
- Extensão em `tool_execute_after`/`hist_add_tool_result`: resultado acima de ~3 mil caracteres é salvo
  em `/a0/usr/chats/<id>/saidas/<passo>-<ferramenta>.txt` e no histórico fica só o começo (~1.500
  caracteres) + o caminho + "leia o arquivo se precisar".
- Vale para página do navegador, terminal, resultado de subagente, buscas.
- Imagens: depois de analisadas, trocar a imagem no histórico pela descrição em texto.

### 3. `contexto.md` como memória da tarefa, sem duplicar — economia estimada 5–10%
- Regra no prompt: o `contexto.md` já está nas instruções; **não ler com `text_editor`**.
- Edição do `contexto.md` devolve só "ok, N linhas" (não o arquivo inteiro).
- Padronizar seções curtas (objetivo, decisões, IDs, pendências) para que o resumo do histórico possa
  ser agressivo sem perder o que importa.

### 4. Manuais de ferramentas sob demanda — economia estimada 5–8%
- Hoje todos os manuais (~30 mil caracteres) vão em toda chamada.
- Manter só uma linha por ferramenta raramente usada (`celular`, `office_artifact`, `scheduler`,
  `parallel`, `analisar_imagens`...) e carregar o manual completo quando o agente for usá-la (como as
  skills já fazem).

### 5. Cache do prompt — reduz o preço do que sobrar
- Ordenar o prompt do mais estável para o mais variável: manuais e regras fixas primeiro; data/hora,
  memórias recuperadas e `contexto.md` por último. Hoje partes que mudam ficam no meio e quebram o cache.
- Medir: o proxy (`bedrock_proxy.py`) passa a registrar `usage` de cada resposta (tokens de entrada,
  em cache e de saída) num arquivo, para sabermos a taxa de acerto real e o custo de verdade.

### 6. Subagente para navegação longa
- Fluxos de 20–50 passos no navegador (ex.: preencher formulário da Meta) rodam num subagente de
  contexto limpo que devolve só o resultado; o agente principal fica pequeno.
- Já existe em parte; padronizar no prompt ("tarefa de navegador com mais de ~10 passos → subagente").

### 7. Memória de longo prazo sob demanda
- A busca automática de memórias/soluções a cada passo injeta texto sempre. Limitar a quantidade e o
  tamanho, e deixar o agente buscar explicitamente quando precisar.

## Ordem de execução

1. **Medir (1 dia de uso):** log por chamada no proxy (`usage` com cache) + extensão que registra o
   tamanho de cada parte do prompt. Sai uma linha de base real.
2. **Alavancas 1 + 3** (só configuração e prompt; reversíveis). Medir de novo.
3. **Alavanca 2** (extensão nova, com teste). Medir.
4. **Alavancas 4 + 5** (reordenar prompt e manuais sob demanda). Medir taxa de cache.
5. **Alavancas 6 + 7** se ainda valer a pena.

Cada etapa: comparar tokens por chamada, custo por tarefa e se o agente continua acertando (rodar a
mesma tarefa de referência antes/depois).

## Meta

Sair de ~80 mil tokens por chamada para **~25–35 mil**, sem perder qualidade — algo como **60–70% menos
custo de entrada** em tarefas longas como a da Meta.
