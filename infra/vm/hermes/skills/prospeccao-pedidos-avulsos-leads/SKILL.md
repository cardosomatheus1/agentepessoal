---
name: prospeccao-pedidos-avulsos-leads
description: "Interpretar e executar avisos curtos do Matheus sobre um perfil da prospecção (\"fulano seguiu a gente\", \"fulano curtiu\", \"fulano respondeu\"): confirmar o que aconteceu na @raiz.connect e registrar na ferramenta prospeccao."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-22
tags: ["aprendizado"]
trigger_patterns:
  - "segui a gente"
  - "seguiu a gente"
  - "começou a seguir"
  - "seguiu de volta"
  - "curtiu"
  - "comentou"
  - "respondeu a gente"
  - "prospeccao"
---

# Avisos curtos do Matheus sobre um perfil da prospecção

Complementa a skill `prospeccao-instagram` (carregue-a junto: conta certa, regras de bloqueio e ferramenta `prospeccao`). Vale para mensagens de uma linha como "@x segui a gente", "@x curtiu", "@x respondeu".

## Como ler a frase
- **"<@x> segui(u) a gente"** quer dizer que **@x passou a seguir a @raiz.connect**. Não quer dizer que a Raiz segue @x. Ler ao contrário leva a conferir o botão "Following" no perfil dele, que só mostra o lado da Raiz e não responde ao que ele contou. O mesmo vale para "curtiu a gente" e "comentou na gente": o sujeito é o perfil citado e o alvo é a Raiz.
- Na dúvida entre as duas leituras, siga a que muda o registro (o perfil agiu sobre a Raiz). A ação de a Raiz seguir alguém só sai pela `proxima`.

## Fluxo
1. Confirme a conta certa (skill prospeccao-instagram, seção 1).
2. Procure o @ no registro: `contexto` (listas "deve receber") ou busca em /a0/usr/prospeccao/matheus.json (`search_files` ou `terminal` com grep). Anote em que etapa ele está e se já recebeu mensagem.
3. Confirme o evento no Instagram, em leitura apenas: abra https://www.instagram.com/accounts/activity/ com `browser_navigate` (ou clique no coração do menu) e leia com `browser_snapshot` procurando "começou a seguir você" com o @ dele. O botão "Following" no perfil dele NÃO prova que ele segue a Raiz. Se a notificação não aparecer, diga isso; o Matheus pode ter visto no celular, então registre mesmo assim com a nota "informado pelo Matheus".
4. Registre: `etapa` com `lead_id` = o @, etapa "interagiu" (ou a etapa mais avançada que ele já tiver), `nota` = "seguiu a Raiz" (onde: direct não se aplica; use o padrão). Se o @ não está no registro, use `entrou` com `handle` e a nota. Isso dá prioridade à 1ª mensagem dele.
5. Chame `caixa_lida` só se estiver numa rodada de execução; num pedido avulso não é preciso.
6. Não siga de volta, não curta e não mande mensagem por conta própria: seguir de volta e a 1ª mensagem saem pela `proxima`/`propor` dentro dos limites. Só proponha mensagem se o Matheus pediu, ou se `contexto` já lista o @ como devido.

## Resposta
- Curta: o que confirmou (e onde viu), o que registrou e em que etapa o perfil está, e o que acontece depois (prioridade na próxima abordagem). Diga o que não conseguiu confirmar.
- Não descreva o perfil dele (bio, seguidores) a não ser que ajude a decidir algo.
