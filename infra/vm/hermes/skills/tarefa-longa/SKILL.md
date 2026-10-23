---
name: tarefa-longa
description: "Pedido longo (muitos passos, muito tempo, vários módulos ou sites; do celular ou de rotina) com plano em disco: sobrevive a reinício, queda, limite de uso e tempo esgotado, retoma sozinho do próximo passo e entrega uma mensagem só no fim, com o arquivo completo."
version: 1.0.0
adaptada_hermes: 2026-10-23
origem: operador
atualizada: 2026-10-23
tags: ["tarefas", "persistência"]
trigger_patterns:
  - "testar de ponta a ponta"
  - "teste completo"
  - "relatório completo"
  - "pesquisa grande"
  - "todos os módulos"
  - "vários sites"
  - "retome a tarefa"
  - "continua"
---

# Tarefa longa: plano em disco, retomada sozinha, entrega no fim

Matheus, 23/10: tarefa longa não pode se perder quando o agente reinicia, a máquina cai, o uso bate no limite ou o
pedido estoura o tempo. O plano fica num arquivo; se parar no meio, o vigia retoma sozinho do próximo passo pendente,
sem ele pedir. Ele recebe UMA mensagem no fim, com o resumo e o arquivo com tudo.

## Quando usar
- 4 passos ou mais, mais de uns 10 minutos, ou vários módulos/sites/contas. Do celular ou de rotina, tanto faz.
- Exemplo que manda: testar o Raiz Connect de ponta a ponta como cliente novo (cadastro, cada módulo, relatório).
- Pergunta rápida, uma busca, um cálculo: não use.

## Como
1. Antes de começar: `tarefa_iniciar(titulo, pedido, passos)`. `pedido` = o que ele escreveu, palavra por palavra.
   Um passo por módulo/site/parte do relatório. Passo que não depende do anterior: `{"titulo": "...", "depende_de": []}`.
2. Em cada passo: `tarefa_passo(id, passo, estado="fazendo")` ao começar; ao terminar,
   `tarefa_passo(id, passo, estado="feito", resultado="...")` com o resultado COMPLETO (vai para o arquivo final;
   achados, números, links, prints citados). Passo feito não se refaz.
3. Não mande mensagens no meio (nada de "terminei o passo 2"). A mensagem de andamento do celular já mostra o passo.
4. No fim: `tarefa_concluir(id, resumo)`: poucas linhas com o principal e o que ele precisa decidir. A ferramenta
   manda o resumo + o arquivo numa mensagem só. Depois responda só: ok

## Ação de fora (mensagem, DM, e-mail, criar conta, postar, pagar, enviar formulário)
- Ao começar o passo: `tarefa_passo(..., estado="fazendo", acao="vou criar a conta teste@... no site X")`.
- Depois de fazer e conferir no próprio sistema: `estado="feito"` com `prova` (id, link, o que leu de volta).
- Na retomada, se o status mostra "ação de fora marcada e NÃO confirmada": CONFIRA no sistema antes de refazer (a conta
  existe? a mensagem já está lá?). Já aconteceu: marque feito com a prova. Não aconteceu: refaça e diga em `conferido`
  o que viu. Nunca recuse refazer "por medo de duplicar": confira e decida pelo que viu.
- As regras de sempre continuam: o que precisa do ok dele, pede ok; nada disso muda as aprovações.

## Precisa do Matheus (captcha/"Resolver aqui", código, senha fora do cofre, decisão)
- `tarefa_passo(..., estado="esperando_matheus", pergunta="...")`: a pergunta vai uma vez ao celular dele. Se você já
  chamou `resolver_aqui`, não repita a pergunta (deixe `pergunta` vazia).
- Siga com os passos que não dependem disso. Sem nada mais para fazer: termine a resposta com "ok".
- Quando ele responder ou apertar "✅ Terminei": `tarefa_status(id)`, mude o passo (`fazendo`/`feito`) e siga.

## Retomada
- O vigia manda "[Aviso automático do vigia de tarefas: ... retome a tarefa <id> ...]": chame `tarefa_status(id)`,
  confira as ações marcadas e siga do próximo passo pendente. Os resultados dos passos feitos estão no status.
- Ele disse "continua" ou "/parar" pausou: `tarefa_status` sem id lista as tarefas dele; siga a que ele quer.
- Passo que não dá de jeito nenhum (3 caminhos tentados): `estado="falhou"` com `erro`, e siga com o resto.
