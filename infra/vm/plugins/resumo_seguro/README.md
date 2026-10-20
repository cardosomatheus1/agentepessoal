# Resumo que não perde detalhes

Numa conversa longa, o Agent Zero resume o histórico antigo com o modelo utilitário ("um parágrafo, ~100
palavras"). Nesse resumo sumiam o @ do lead, o `acao_id`, o id da rotina e o caminho
`/a0/usr/chats/<conversa>/saidas/NNNN-…txt` onde o `resultados_grandes` guardou o texto inteiro. Depois disso,
o agente não achava mais o arquivo.

Agora, junto de cada resumo, vai um bloco curto, tirado do trecho resumido por regex (sem modelo):

```
[resumo_seguro] Copiado literalmente do trecho resumido:
## Falas dele literais (as mais novas por último)
» Não manda pro "@doce.lar" ainda, só amanhã às 9h
Âncoras: /a0/usr/chats/<id>/saidas/0007-browser.txt · acao_id=3f2a1b · uuid=laMIuaPt · @zen.marmitas · https://…
Texto completo: os resultados longos ficam em /a0/usr/chats/<id>/saidas/ (…); as mensagens recentes, inteiras, no registro /a0/usr/chats/<id>/chat.json.
```

- **Âncoras:** arquivos de `saidas/`, `acao_id`, uuids e ids de rotina, @ (sem e-mail nem `@property`), links (sem
  os que têm token, chave ou código na URL) e outros caminhos. Os mais recentes vêm primeiro, um de cada tipo por
  vez, para nenhum tipo tomar o bloco inteiro. Âncora que o resumo do modelo já traz não se repete.
- **Falas:** as 8 últimas mensagens do usuário no trecho, literais (até 400 caracteres cada), na seção
  "Falas dele literais".
- **Resumo de resumo:** quando o resumo é resumido de novo, as âncoras e as falas do bloco anterior seguem para o
  bloco novo.
- **Tamanho:** no máximo 3.500 caracteres, e nunca mais que metade do que o resumo economizou. Assim o histórico
  sempre diminui; se crescesse, o Agent Zero pararia com "History compression stalled".
- **Resumo que falha:** o Agent Zero chama o modelo antes de trocar qualquer mensagem. Se a chamada der erro,
  nada muda (o erro segue como antes). Resposta vazia apagaria as mensagens resumidas; agora ela vira erro
  (`ResumoVazio`) e o histórico fica inteiro.
- **Cache do prompt:** o mesmo trecho sempre dá o mesmo bloco (sem hora nem sorteio). O bloco só entra quando o
  histórico já é resumido, que é quando o cache se perde de qualquer jeito (ver `cache_prompt`).

| Arquivo | O que faz |
|---|---|
| `extensions/python/_functions/agent/Agent/call_utility_model/end/_50_ancoras.py` | no fim de `Agent.call_utility_model` (`@extensible`), e só quando o system é `fw.topic_summary.sys.md` (resumo de tópico e de bloco do `helpers/history.py`), anexa o bloco |
| `helpers/ancoras.py` | extração, teto e montagem do bloco; `bloco_do_registro` faz o mesmo a partir do registro de uma conversa |

Ideia tirada do Hermes Agent (MIT), `agent/context_compressor.py`: `_build_anchor_index`,
`_build_verbatim_user_section` e `_build_recovery_footer`.

**O que não dá para fazer sem mexer no Agent Zero:** o Hermes, quando o resumo falha, segue sem resumir e espera
60, 300 e 900 s antes de tentar de novo. No Agent Zero, o erro do resumo sobe por `_90_organize_history_wait.py`,
e o turno termina com erro. Não há gancho para "seguir sem resumir", e uma espera aqui só faria o agente falhar
sem nem tentar. Por isso, as esperas não foram aplicadas.

## 20/10: resumo com seções fixas, menos vezes e nunca da tarefa em andamento

Queixa do Matheus: o agente perde contexto, responde outra coisa e dá passos pequenos. No Agent Zero
(`/a0/helpers/history.py`), passando do limite (`ctx_length` 200.000 × `ctx_history` 0,25 = 50 mil tokens), o tópico
atual é resumido primeiro quando é a maior parte (`compress_attention` 0,65: o meio da tarefa vira um parágrafo de ~100
palavras), os tópicos antigos ficam só com o pedido e a resposta, e cada pedaço é um resumo separado.

Agora (`helpers/compressao.py`), quando passa do mesmo limite:

1. **Poda:** resultados de ferramenta com 1.500+ caracteres, menos os 3 últimos, viram uma linha: ferramenta,
   tamanho, o começo, as âncoras e onde está o texto inteiro (`saidas/`). Só na hora da compressão, quando o cache
   já se perde (nunca entre um passo e outro).
2. **A tarefa em andamento fica inteira:** do pedido atual dele (o `msg_id` que o `objetivo_vivo` guarda; "continua"
   e "e aí?" não mudam) até o fim. Sem o `objetivo_vivo`, a partir da última mensagem dele.
3. **Um resumo só, com seções fixas** (`prompts/fw.topic_summary.sys.md`, que substitui o do Agent Zero pelo mesmo
   nome): Objetivo atual (nas palavras dele), Feito (com resultados e ids), Pendente, Próximos passos, Decisões e
   preferências ditas nesta conversa, e o bloco deste plugin com as Falas dele literais e as âncoras.
4. **O resumo seguinte atualiza o anterior:** o modelo recebe "Resumo anterior" + "Mensagens novas" e atualiza seção
   por seção, sem resumir o resumo. O anterior fica guardado dentro do novo (registro da conversa).
5. **Fundo de uma vez:** fica o que cabe em 45% do limite (a tarefa e os tópicos mais recentes inteiros); o resto
   vai para o resumo, numa chamada só ao modelo.
6. Só se a tarefa em andamento, já podada, passar de 80% do limite, os tópicos mais antigos dela entram no resumo; e
   só se o último tópico sozinho não couber entra o corte do próprio Agent Zero, dentro desse tópico.

Gancho: os arquivos `message_loop_end/_10_organize_history.py` e `message_loop_prompts_before/_90_organize_history_wait.py`
deste plugin têm o nome dos do núcleo e são carregados no lugar deles (extensão de plugin com o mesmo nome substitui a
do núcleo); só trocam a função de compressão. O `/a0` não é editado. A suíte confere o md5 dos arquivos do núcleo:
se o Agent Zero for atualizado e eles mudarem, ela falha até as cópias serem revistas.

**Voltar à compressão do Agent Zero sem implantar:** criar `/a0/usr/plugins/resumo_seguro/compressao_a0` (no
contêiner); apagar o arquivo liga de novo.

**Medido (20/10):** na simulação com o `history.py` real (6 formatos de conversa, 50 mil e 80 mil tokens), as
chamadas ao modelo de resumo caem de 113 para 19 e a tarefa em andamento é resumida 1 vez em vez de 18 (a única é
uma tarefa de 150 passos maior que o limite). O número de compressões fica parecido (27 → 30): na conversa com vários
assuntos o Agent Zero já corta fundo (tópicos antigos ficam só com pedido e resposta), e o que se guarda inteiro
agora é maior. Para resumir menos vezes de verdade, a alavanca é `ctx_history` (de 0,25 para 0,4 no preset: as
nossas compressões caem de 19 para 11 nos mesmos formatos). Nas conversas reais da VM (em memória, sem chamar o modelo), a "Aplicação de Playbooks" (51 mil tokens hoje)
ficaria com 21 mil e a tarefa inteira (10 resultados podados), contra 34 mil com a tarefa resumida no Agent Zero.

Ideias do Hermes Agent (MIT), `agent/context_compressor.py`: resumo estruturado e iterativo, poda de saídas de
ferramenta antes do resumo e cauda protegida.

Testes: `tests/suite.py` e `tests/compressao.py` (o teste com o `Topic`/`Bulk` reais do Agent Zero só roda dentro do contêiner).
