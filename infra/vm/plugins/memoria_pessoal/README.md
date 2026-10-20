# Memória pessoal

Três níveis de contexto, todos em `/a0/usr` (disco da VM + backup no S3):

| Nível | Onde fica | Quem enxerga |
|---|---|---|
| Sobre você | `/a0/usr/memoria/usuarios/<login>.md` (uma por pessoa, pelo login; ferramenta `ficha`) | Todas as conversas e agentes da pessoa |
| Decisões em vigor | `/a0/usr/memoria/decisoes/<login>.json` (`helpers/decisoes.py`) | Todas as conversas da pessoa: o agente segue em vez de perguntar de novo |
| Agente | Projeto do Agent Zero (`/a0/usr/projects/<agente>/`), com memória vetorial isolada | Só as conversas daquele agente |
| Conversa | `/a0/usr/chats/<id>/contexto.md` e `/a0/usr/chats/<id>/anexos/` | Só aquela conversa (apagada junto com ela) |

A extensão injeta as fichas e as decisões no prompt de sistema a cada turno e instrui o agente a mantê-las
atualizadas.

## Decisões (revisão de 12/10, §4.2)
- Uma decisão em vigor por `tema` (nome curto do assunto, ex.: `aprovacoes.instagram`). Decidir de novo no mesmo
  tema substitui a anterior, que fica no histórico (`substituida`, com quem e quando).
- Ferramenta `decisao`: `registrar` (com as palavras da pessoa em `citacao`), `listar`, `historico`, `revogar`.
- Gravação com trava de arquivo e troca atômica; arquivo ilegível é erro, nunca "sem decisões".
- Correção feita pelo operador: pela função `registrar`/`revogar` com `por="operador: <motivo>"`, nunca editando o
  JSON.

## Ficha com teto e proteção (14/10, do Hermes)
- Ferramenta `ficha`: `add`, `patch` (troca um trecho de uma entrada, ou a entrada inteira pelo número), `remove`,
  `listar`. Uma entrada por linha `- …`, teto de 4.000 caracteres: cheia, recusa e devolve as entradas numeradas para o
  agente juntar ou tirar. Duplicata (sem acento/caixa/pontuação) é recusada.
- `helpers/protecao.py` recusa ordem disfarçada de fato ("pode enviar sem pedir ok", "sempre envie…"), injeção
  ("ignore as instruções", "você agora é…", "não conte ao Matheus"), segredo, caractere invisível e texto de terceiros
  (`⟦DADO EXTERNO`, "o lead disse…", e-mail colado). Rotina agendada e conversa de gatilhos não mexem na ficha.
- Mesma trava e troca atômica das decisões; cada mudança vai para `usuarios/<login>.diario.jsonl`.
- **Migração** (uma vez, depois de implantar): `python3 infra/operador/ficha.py ver` mostra o resultado sem gravar;
  `python3 infra/operador/ficha.py migrar --motivo "..."` grava, guardando o original em
  `usuarios/<login>.antes-ficha-<data>.md`. Até migrar, a ficha antiga continua no prompt e a ferramenta não grava.
  Simulado em 14/10 numa cópia da ficha do Matheus: 18 entradas, 2.722/4.000, nenhuma recusada.

## Revisor depois da conversa (14/10, do Hermes `background_review.py`)
- `extensions/python/monologue_end/_60_revisor.py`, só na conversa do celular (`whatsapp_de`), nunca em rotina
  agendada nem gatilhos; roda numa thread, depois da resposta. Mensagens digitadas no app não contam
  (`user_message_ui/_20_veio_do_app.py`): os scripts do operador escrevem lá como `matheus`.
- A cada 8 mensagens dele (ou 3 paradas há 4 h), Luna (esforço baixo) propõe; o código grava só o que tem a frase
  LITERAL dele: decisão nova (`decisoes.registrar(por="revisor")`), correção de rotina existente
  (`rotinas/helpers/rotinas.py` `corrigir(por="revisor")`; sem esse helper, desligado), fato na ficha (`ficha.adicionar`).
  Trocar uma decisão em vigor vira pergunta ("Troco por …? Responda «troca a N»"). Nunca revoga, troca nem apaga.
- No fim de cada tarefa com 5+ ferramentas que terminou com resposta, oferece salvar como rotina ("Quer que eu salve
  '<nome>' como rotina?"): no máximo 1 por dia, nome da classe da tarefa (sem data, número, @, "hoje"), nunca uma que
  já existe ou que já foi sugerida. Quem cria é o agente, com `salvar_rotina`, se ele disser sim.
- Um aviso por revisão, tipo `progresso` (fica nos "últimos avisos" da conversa do celular, para o agente entender
  «desfaz a N», «tira da ficha: …», «tira da rotina X»). Estado: `/a0/usr/memoria/revisor/<login>.json`.

## Buscar em conversas antigas (14/10, do Hermes `session_search_tool.py`)
- Ferramenta `lembrar`: SQLite FTS5 (sem modelo, sem acento) em `/a0/usr/memoria/busca.db`, atualizado a cada busca
  (só as conversas cujo arquivo mudou, só o que é novo; até 20 s por busca na primeira montagem). Devolve trechos com
  data e id da conversa. Cada um só vê as próprias conversas (dono da conversa); conversas de ajudantes ficam fora;
  rotinas aparecem depois, marcadas. Conversa apagada sai do índice; índice quebrado é refeito.

## Prompt enxuto (20/10)
- O `contexto.md` e os anexos da conversa saíram das instruções (mudavam durante a conversa e faziam o Bedrock reler
  o prompt inteiro): vão no fim, no bloco `contexto_conversa`, uma vez por mensagem e só quando mudam (`cache_prompt`).
- "Velocidade" (parar quando terminou, conferir no máximo 2 vezes) ficou nas "Regras que valem sempre" (`prompt_enxuto`).
- Rodada agendada que terminou `SEM NOVIDADE` não é memorizada (eram 2+ chamadas ao modelo por rodada, ~40 rodadas
  por dia, para guardar nada).
