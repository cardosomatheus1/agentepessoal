# Ações em paralelo

Quando o modelo pede várias ações numa resposta só, o Agent Zero rodava uma depois da outra. Agora, como no Hermes Agent
(MIT, NousResearch, `agent/tool_dispatch_helpers.py` e o `PARALLEL_TOOL_CALL_GUIDANCE` de `agent/prompt_builder.py`):

- **ao mesmo tempo:**
  - buscas (`search_engine`), documentos (`document_query`), memória (`memory_load`, `lembrar`), `consultar_sol`;
  - consultas à Pasta (`cerebro` consultar/assuntos), `fios` listar e skills (search/list/load/read_file);
  - leituras do Gmail, Agenda, Drive e GitHub pela `ferramentas_extras`;
  - arquivos (`text_editor`) quando nenhuma escrita cai num caminho que outra ação do grupo lê ou escreve;
- **uma de cada vez, na ordem, do jeito do Agent Zero:**
  - navegador, celular, terminal, mensagens, prospecção, ajudantes e a resposta final;
  - qualquer ferramenta que não está na lista: ferramenta desconhecida é barreira, como no Hermes.

| Arquivo | O que faz |
|---|---|
| `helpers/plano.py` | quem pode ir junto e a divisão da resposta em grupos, na ordem; o texto que orienta o modelo |
| `helpers/executar.py` | roda um grupo: conferências de antes de cada ferramenta, as execuções juntas, depois resultado, conferências e histórico de cada uma na ordem pedida |
| `extensions/python/agent_init/_20_acoes_paralelas.py` | troca `Agent.process_llm_result_tools` na classe, uma vez por processo, só se o código do Agent Zero for o conhecido (md5 dos dois métodos); `/a0` não é editado |
| `extensions/python/system_prompt/_13_acoes_paralelas.py` | no modo nativo, diz ao modelo para pedir juntas as ações que não dependem umas das outras |

**Garantias (testadas):**
- os resultados entram no histórico na ordem em que o modelo pediu;
- as conferências `tool_execute_before/after` rodam para cada ferramenta;
- uma ação que falha vira resultado de erro e as outras não se perdem;
- mensagem nova da pessoa no meio para a vez, como antes;
- uma ação sozinha, ou nada que possa ir junto, segue pelo caminho do Agent Zero sem mudança.

**Agent Zero atualizado:** se os dois métodos mudarem, o plugin não instala, avisa no log
(`acoes_paralelas: versao diferente: …`) e tudo roda como o Agent Zero roda.

**Desligar sem implantar:** criar `/a0/usr/plugins/acoes_paralelas/desligado`.
