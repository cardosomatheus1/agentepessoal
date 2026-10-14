# aprovacoes

Antes de uma ação de risco, um **revisor separado** identifica o tipo da ação e aplica a **sua regra**:

| Regra | O que acontece |
|---|---|
| permitir | o agente faz sozinho |
| perguntar | o agente **para**; aparece um cartão **Aprovar / Nesta tarefa / Sempre permitir / Recusar** na conversa e, se você tem WhatsApp ou Telegram, uma mensagem com Aprovar / Sempre permitir / Recusar |
| nunca | bloqueado, mesmo com "sempre permitir" |

Padrão: pagamento, compra e trocar senha/2FA = **nunca**; termos, enviar para análise, mensagem a
terceiros, publicar, apagar, contas reais e produção = **perguntar**. Edite em **Configurações → Plugins →
Aprovações e regras**.

Instagram: **mensagens** no Instagram não pedem aprovação e cada uma é avisada no celular (Matheus, 12/10: "pode
me avisar que foi feito"). Publicar (pode ser anúncio) e cancelar envio/apagar continuam pedindo. Desliga com
`instagram_sem_perguntar: false`.

Como decide:
- Só passam pelo revisor ações que podem mudar algo fora do agente: cliques/teclas no navegador cuja
  intenção fala em enviar, aceitar, pagar, publicar, apagar…; comandos de terminal destrutivos (`rm -`,
  `git push`, `DROP`, `aws … delete`, `curl -X POST` …); ferramentas MCP que escrevem.
- O revisor (Luna, esforço baixo) vê **só** a ferramenta, os argumentos e a intenção declarada pelo
  agente — nunca o conteúdo da página, que pode trazer instruções maliciosas. Ele só **classifica**; a
  decisão vem da sua regra, de forma determinística.
- Se o revisor falhar, a ação **espera você**. Se o aviso no WhatsApp falhar, o cartão na conversa continua.
- **Nesta tarefa** (14/10): libera o mesmo tipo de ação (a categoria) até a tarefa terminar; nunca para sempre, nunca
  acima de uma regra "nunca". O que ela libera não conta na proteção contra repetição (3ª aprovação parecida em 10 min).
  No celular ainda não aparece: o Telegram e o WhatsApp levam só 3 botões e a resposta do botão "tarefa" não existe no
  plugin `whatsapp` (`CELULAR_TAREFA` em `helpers/revisor.py` liga quando eles mudarem).
- Responder `aprovar`, `nesta tarefa`, `sempre` ou `recusar` na conversa também vale. Qualquer outra mensagem cancela a
  ação e vai para o agente normalmente.
- Sem resposta em `espera_minutos` (padrão 6 h), a ação é cancelada. Enquanto espera, a VM pode hibernar;
  a resposta pelo WhatsApp a acorda e a espera continua.
- Recusa ou bloqueio: a ferramenta não roda e o agente recebe "não foi executado; não tente de novo nem
  por outro caminho".
- Cada decisão vai para o log do contêiner: `aprovacoes: <ferramenta> -> <categoria>/<decisão>: <resumo>`.
