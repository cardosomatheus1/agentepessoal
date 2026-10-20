# Segundo Cérebro: a Pasta

A Pasta (`/a0/usr/segundo_cerebro/pasta`) é a única fonte do Segundo Cérebro do Matheus (ADR `docs/adr/0001`,
glossário em `GLOSSARY.md`). Estrutura dos guias da Playbook Lab: `CLAUDE.md`, `Contexto/` (6 arquivos),
`Decisoes/`, `Pendencias/`, `Assuntos/`, `Reunioes/`, `Notas-do-dia/`, `Projetos/`, `Documentos/`, `Arquivo-morto/`.

- **Quem escreve**: `decisoes.py` (memoria_pessoal), `fios.py` (fios_soltos: pendências) e `ficha.py` (perfil) passaram
  a gravar aqui para o dono depois da migração; `helpers/assuntos.py` cuida dos Assuntos. Nada se apaga: o que sai vai
  para `Arquivo-morto/`. Histórico: a Pasta é um repositório git (uma versão por hora e a cada mudança).
- **Anotação automática** (`extensions/.../monologue_end/_62_cerebro_captura.py` + `helpers/captura.py`): depois de cada
  mensagem dele no celular, um modelo barato propõe Decisões, Pendências e Assuntos; só entra o que tem as palavras dele
  citadas; os da mesma frase ficam ligados; vai uma linha "📌 Anotei …". Errado → `cerebro` acao=desfazer.
- **Nota do dia** às 20h (Bahia) com resumo de 3 linhas e convite para a próxima seção da entrevista
  (`job_loop/_58_cerebro.py`, `helpers/dia.py`). **Auditoria** (checagens do OS Optimizer) no dia 1 de cada mês.
- **Reuniões** (`helpers/reunioes.py`, único que escreve em `Reunioes/`): uma nota por reunião
  (`AAAA-MM-DD-<slug>.md`: resumo, participantes, Decisões e próximos passos com links, `indice.md`); gravar de novo
  completa, nunca apaga. Vem do pós-reunião do `auxiliar` (a resposta dele vira fios e a nota, ligada a eles) ou de
  `cerebro` acao=reuniao (reunião que ele conta no Telegram; próximos passos novos viram Pendências pelo `fios.py`).
- **Ferramenta `cerebro`**: consultar, assunto(s), reuniao, desfazer, contexto (entrevista, só grava com o ok dele),
  nota_do_dia, auditoria.
- **Operador**: `python3 infra/operador/cerebro.py migrar --motivo "…"` (uma vez), `estado`, `auditoria`, `nota`.
