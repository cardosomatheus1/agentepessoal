# Memória pessoal

Três níveis de contexto, todos em `/a0/usr` (disco da VM + backup no S3):

| Nível | Onde fica | Quem enxerga |
|---|---|---|
| Sobre você | `/a0/usr/memoria/usuarios/<login>.md` (uma por pessoa, pelo login) | Todas as conversas e agentes da pessoa |
| Agente | Projeto do Agent Zero (`/a0/usr/projects/<agente>/`), com memória vetorial isolada | Só as conversas daquele agente |
| Conversa | `/a0/usr/chats/<id>/contexto.md` e `/a0/usr/chats/<id>/anexos/` | Só aquela conversa (apagada junto com ela) |

A extensão injeta as fichas no prompt de sistema a cada turno e instrui o agente a mantê-las atualizadas.
