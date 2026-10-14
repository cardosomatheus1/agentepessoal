# Resumo que não perde detalhes

Numa conversa longa, o Agent Zero resume o histórico antigo com o modelo utilitário ("um parágrafo, ~100
palavras"). Nesse resumo sumiam o @ do lead, o `acao_id`, o id da rotina e o caminho
`/a0/usr/chats/<conversa>/saidas/NNNN-…txt` onde o `resultados_grandes` guardou o texto inteiro. Depois disso,
o agente não achava mais o arquivo.

Agora, junto de cada resumo, vai um bloco curto, tirado do trecho resumido por regex (sem modelo):

```
[resumo_seguro] Copiado literalmente do trecho resumido:
Últimas falas do usuário:
» Não manda pro "@doce.lar" ainda, só amanhã às 9h
Âncoras: /a0/usr/chats/<id>/saidas/0007-browser.txt · acao_id=3f2a1b · uuid=laMIuaPt · @zen.marmitas · https://…
Texto completo: os resultados longos ficam em /a0/usr/chats/<id>/saidas/ (…); as mensagens recentes, inteiras, no registro /a0/usr/chats/<id>/chat.json.
```

- **Âncoras:** arquivos de `saidas/`, `acao_id`, uuids e ids de rotina, @ (sem e-mail nem `@property`), links (sem
  os que têm token, chave ou código na URL) e outros caminhos. Os mais recentes vêm primeiro, um de cada tipo por
  vez, para nenhum tipo tomar o bloco inteiro. Âncora que o resumo do modelo já traz não se repete.
- **Falas:** as 3 últimas mensagens do usuário no trecho, literais (até 300 caracteres cada).
- **Resumo de resumo:** quando o resumo é resumido de novo, as âncoras e as falas do bloco anterior seguem para o
  bloco novo.
- **Tamanho:** no máximo 2.000 caracteres, e nunca mais que metade do que o resumo economizou. Assim o histórico
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

Testes: `tests/suite.py` (o teste com o `Topic`/`Bulk` reais do Agent Zero só roda dentro do contêiner).
