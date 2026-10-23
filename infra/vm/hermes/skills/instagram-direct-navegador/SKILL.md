---
name: instagram-direct-navegador
description: "Enviar mensagem no Direct do Instagram pelo navegador do agente (conta @raiz.connect): digitar no campo com o script da ferramenta prospeccao, achar o botão Enviar, limpar texto duplicado e confirmar que saiu. Use também quando o Matheus manda enviar algo que o revisor recusou."
version: 1.0.2
adaptada_hermes: 2026-10-23
origem_a0: 1.0.2
origem: aprendizado
atualizada: 2026-10-21
tags: ["aprendizado"]
trigger_patterns:
  - "direct instagram"
  - "enviar mensagem instagram"
  - "campo de mensagem"
  - "botão Send"
  - "texto duplicado"
  - "acima do revisor"
  - "enviar o link"
  - "ordem_matheus"
---

# Enviar mensagem no Direct do Instagram (navegador)

Vale quando o envio vai pela página `instagram.com/direct/t/...` no navegador. A regra de quando e o que enviar está em prospeccao-instagram (ferramenta `prospeccao`, cotas, revisor). Esta skill cobre só a mecânica e a ordem do Matheus.

## Quando o Matheus manda enviar
1. Um pedido dele de envio específico ("envia o link", "minha decisão deve ser acima do revisor") já é a autorização. Não pergunte de novo "posso enviar?". Se faltar só o texto, use o último texto proposto, curto, e envie. Perguntar de novo devolve a decisão que ele já tomou.
2. Pela ferramenta `prospeccao`: `propor` com tipo `resposta` e `ordem_matheus` = as palavras exatas dele; depois `proxima`. Se a ação vier PRÉ-APROVADA, o texto que ela devolve (pode trazer parâmetro de rastreio no link, ex.: `?o=ig-b`) é o texto a enviar, EXATAMENTE. Não troque por outra versão e não diga no relato que usou outro link.
3. Registre a decisão com `decisao` (só o que ele disse, sem ampliar para outros textos) e avise no fim o que saiu e para quem.

## Passo a passo
1. Abra a conversa certa com `browser_navigate` na URL da conversa. Leia com `browser_snapshot` e confira o nome do perfil e a última mensagem dele.
2. **Digite com o script que a `proxima` devolve (não com `browser_type`).** Ordem: (a) `browser_click` na ref do campo de mensagem (o campo editável); (b) `browser_press` `Control+a`; (c) em OUTRA chamada, `browser_press` `Backspace` (nunca as duas em paralelo); (d) rode o script de digitação com `browser_console` (expression = o script): ele confere que o campo está vazio, insere o texto uma vez e espera estabilizar. Resposta `OK` = siga. `DUPLICADO` ou `CAMPO NÃO ESTÁ VAZIO` = repita (a)–(d), no máximo 2 vezes.
3. Rode o script de CONFERÊNCIA com `browser_console` logo antes de enviar. Só `PODE ENVIAR` libera; qualquer outra resposta: não envie.
4. Releia com `browser_snapshot`: o botão **Send** aparece como botão "Send" com ref nova. Envie com `browser_click` nessa ref (não no campo) ou com `browser_press` `Enter` com o foco no campo. Clicar de novo no campo, ou por coordenada, não envia e dispara o aviso de ação repetida.
5. Confira no `browser_snapshot` seguinte: a mensagem aparece UMA vez como da @raiz.connect e o campo voltou vazio (aparecem "Voice Clip / Add Photo" em vez de "Send"). Só então diga "enviado" e chame `prospeccao` `resultado` com o que viu.

## Armadilhas
- **`browser_type` no campo do Direct duplica o texto** (o "conferido" mostra a frase repetida), porque o campo é um contenteditable que soma ao que já tem. Por isso o texto entra pelo script de `insertText` da `proxima`, via `browser_console`. Se já duplicou, não envie: limpe com `browser_click` no campo + `browser_press` Control+a + `browser_press` Backspace (chamadas separadas) e rode o script.
- Antes de desistir e devolver a tarefa, execute de fato a limpeza e o script. Não relate "Ctrl+A, Backspace e recarregar não resolveram" sem ter feito cada um: relate só o que foi executado.
- Depois de limpar, confira com `browser_snapshot` (ou o script de conferência) antes de enviar. Nunca envie mensagem com a frase repetida.
- Se a ferramenta avisar que repetiu a mesma ação, mude de alvo (Send, Enter, script), não repita o clique.
- Não desista com "preciso do seu OK" quando o pedido dele já é o OK: falhou a mecânica, tente script, botão Send e Enter antes de devolver a tarefa. Só peça ajuda ao Matheus (limpar pelo celular) depois de esgotar isso.
- Se o Instagram mostrar bloqueio/limite/verificação, pare e mande `bloqueio: true` na `prospeccao`.
