# Segundo Cérebro: a Pasta é a fonte única; o site só mostra

Em 20/10/2026 o Matheus decidiu, comparando com os guias da Playbook Lab ("Setup inicial do OS" e "OS Optimizer"), que o
Segundo Cérebro passa a ser uma pasta de arquivos Markdown na VM (Context/, Projects/, Meetings/, Daily/, Documents/,
mais Decisões, Pendências e Assuntos), escrita só pelo agente a partir das conversas no Telegram, com cópia diária num
repositório privado no GitHub. O site `/segundo-cerebro` (Next, na VM) só lê a Pasta e mostra páginas, links e o mapa
de conexões. As 35 decisões, 33 fios e a ficha que existiam em JSON/Markdown separados são migrados uma vez e viram
arquivo morto (só leitura): nada de dois lugares gravando a mesma coisa.

## Considered Options

- Manter os stores separados (decisoes/*.json, fios/*.json, ficha) e o painel lendo nove fontes: rejeitado, porque
  cada tipo novo (Assunto, Pessoa, Reunião) exigiria outro store e o painel já divergia do contrato.
- Banco de dados ou busca vetorial: rejeitado, os guias pedem arquivos que o modelo lê direto, sem RAG.
- Obsidian/Drive como origem: adiado; a Pasta pode ser aberta no Obsidian depois, mas a VM é onde o agente escreve.
