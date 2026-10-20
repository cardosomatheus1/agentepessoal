# Delegados: Hermes e OpenClaw com o Agent Zero orquestrando

O Agent Zero é o orquestrador. Para cada tarefa ele decide se faz sozinho ou entrega ao Hermes ou ao OpenClaw.

- `delegar` (20/10): o Hermes ou o OpenClaw roda a tarefa com **as ferramentas deles** (terminal, arquivos, internet,
  navegador Chromium, Python/node) numa caixa Docker própria no host (`infra/vm/caixa_delegados.py`), sem nada do Matheus
  montado: sem cofre, contas, navegador logado nem acesso ao proxy além do modelo. Volta a resposta, as ferramentas usadas
  e os arquivos de `/trabalho/saida/`, copiados para `/a0/usr/workdir/delegados/<id>/`.
- Quem faz o quê: `helpers/escolha.py` (contas, mensagens, dinheiro e prospecção ficam no A0; código e dados → Hermes;
  pesquisa na web e segunda opinião → OpenClaw). O agente pode escolher o motor ele mesmo.
- `text_delegate` (17/10) continua: uma análise só de texto, rápida, sem caixa.

Limites da caixa: 3 GB de memória, 2 CPUs, até 30 min, 2 tarefas ao mesmo tempo, 400 chamadas ao modelo por tarefa,
arquivos de entrada só das pastas de trabalho (até 10, 25 MB cada), saída até 200 MB.
