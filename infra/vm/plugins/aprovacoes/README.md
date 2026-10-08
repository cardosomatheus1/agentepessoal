# aprovacoes

Antes de uma ação de risco, um **revisor separado** identifica o tipo da ação e aplica a **sua regra**:

| Regra | O que acontece |
|---|---|
| permitir | o agente faz sozinho |
| perguntar | o agente **para**; aparece um cartão **Aprovar / Sempre permitir / Recusar** na conversa e, se você tem WhatsApp, uma mensagem com os mesmos botões |
| nunca | bloqueado, mesmo com "sempre permitir" |

Padrão: pagamento, compra e trocar senha/2FA = **nunca**; termos, enviar para análise, mensagem a
terceiros, publicar, apagar, contas reais e produção = **perguntar**. Edite em **Configurações → Plugins →
Aprovações e regras**.

Como decide:
- Só passam pelo revisor ações que podem mudar algo fora do agente: cliques/teclas no navegador cuja
  intenção fala em enviar, aceitar, pagar, publicar, apagar…; comandos de terminal destrutivos (`rm -`,
  `git push`, `DROP`, `aws … delete`, `curl -X POST` …); ferramentas MCP que escrevem.
- O revisor (Luna, esforço baixo) vê **só** a ferramenta, os argumentos e a intenção declarada pelo
  agente — nunca o conteúdo da página, que pode trazer instruções maliciosas. Ele só **classifica**; a
  decisão vem da sua regra, de forma determinística.
- Se o revisor falhar, a ação **espera você**. Se o aviso no WhatsApp falhar, o cartão na conversa continua.
- Responder `aprovar`, `sempre` ou `recusar` na conversa também vale. Qualquer outra mensagem cancela a
  ação e vai para o agente normalmente.
- Sem resposta em `espera_minutos` (padrão 6 h), a ação é cancelada. Enquanto espera, a VM pode hibernar;
  a resposta pelo WhatsApp a acorda e a espera continua.
- Recusa ou bloqueio: a ferramenta não roda e o agente recebe "não foi executado; não tente de novo nem
  por outro caminho".
- Cada decisão vai para o log do contêiner: `aprovacoes: <ferramenta> -> <categoria>/<decisão>: <resumo>`.
