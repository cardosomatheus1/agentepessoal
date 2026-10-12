# Memória pessoal

Três níveis de contexto, todos em `/a0/usr` (disco da VM + backup no S3):

| Nível | Onde fica | Quem enxerga |
|---|---|---|
| Sobre você | `/a0/usr/memoria/usuarios/<login>.md` (uma por pessoa, pelo login) | Todas as conversas e agentes da pessoa |
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
