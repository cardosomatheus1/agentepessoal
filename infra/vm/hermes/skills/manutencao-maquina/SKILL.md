---
name: manutencao-maquina
description: "Cuidar da memória e do navegador da máquina do agente: quando fechar abas, o que a limpeza automática já faz, como ver se a máquina está apertada e o que fazer se travar. Use antes de tarefas longas de navegador e quando o Matheus disser que o agente está lento ou travou."
version: 1.0.0
adaptada_hermes: 2026-10-23
origem_a0: 1.0.0
tags: ["manutenção", "memória", "navegador", "abas", "lento", "travou", "limpeza"]
trigger_patterns:
  - "lento"
  - "travou"
  - "travado"
  - "memória"
  - "limpeza"
  - "abas"
---

# Manutenção da máquina do agente

A máquina tem 16 GB. O que mais come memória é o navegador: cada conversa e cada rodada agendada abre abas, e elas
ficavam abertas para sempre. Em 10/10 chegaram a 75 processos do Chromium (11,8 GB) e a máquina congelou por
30 minutos, até ser reiniciada.

## O que já é automático

1. **Plugin `limpeza`** (dentro do agente, a cada 5 min): fecha as abas de conversas que não estão rodando e estão
   paradas há 20 min; com menos de 3 GB livres, há 5 min; com menos de 1,5 GB, todas as que não estão rodando agora.
   Nunca fecha a conversa que está trabalhando. Registro em `/a0/usr/limpeza/log.jsonl`.
2. **`memguard`** (na máquina, a cada 1 min): se a memória livre ficar abaixo de 700 MB por 3 minutos seguidos,
   reinicia só o contêiner do agente (dados e logins ficam no disco). Registro em
   `/var/lib/agentepessoal/memguard.log`.

## O que você faz

- **Uma aba por tarefa.** Para ir a outra página, use `browser_navigate` com o novo endereço na mesma aba, em vez de
  abrir outra. Não deixe abas "para depois".
- **Antes de uma tarefa longa de navegador** (busca de leads, análise de anúncios), confira a memória com `terminal`:
  `free -m` (coluna "available"). Abaixo de 3 GB, não comece antes de liberar memória (veja abaixo).

## Se o Matheus disser que travou ou está lento

1. Com `terminal`: `free -m` e `ps -eo rss,comm --sort=-rss | head` — veja quanto o Chromium está usando.
2. Com `terminal`: `tail -5 /a0/usr/limpeza/log.jsonl` — a limpeza automática está agindo?
3. Explique em uma linha o que viu e o que já foi feito. Reiniciar a máquina ou o contêiner é com o operador
   (sessão do Claude Code), não com você.
