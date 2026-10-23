---
name: login-sites-navegador
description: "Entrar em sites e painéis (portais de parceiros, 99Food, iFood, Nexos, redes sociais) pelo navegador do agente usando senhas do cofre, ou entregar o navegador ao Matheus (botão \"Resolver aqui\") para ele logar; e o que fazer quando o botão Entrar não responde, a página dá erro, o certificado é recusado ou o site recusa."
version: 1.0.6
adaptada_hermes: 2026-10-23
ressemear: resolver-aqui-1
origem_a0: 1.0.5
origem: aprendizado
atualizada: 2026-10-22
tags: ["aprendizado"]
trigger_patterns:
  - "login"
  - "entrar na conta"
  - "senha do cofre"
  - "secret"
  - "99Food"
  - "iFood"
  - "portal iFood"
  - "Nexos"
---

# Login em sites pelo navegador (com o cofre)

## Fluxo (você faz o login)
1. Abra a URL do painel com `browser_navigate`. Portais costumam redirecionar para uma página de login de outro domínio (ex.: Cognito). Isso é normal, continue nela.
2. Leia a página com `browser_snapshot`. Os campos e botões aparecem com refs (`@e12`). Use essas refs, não coordenadas: clique por coordenada erra o campo e o texto cai no lugar errado.
3. **Escolha o método de login que o Matheus (ou o operador) indicou no pedido.** Se ele disse "Entrar com acesso único" / SSO, clique nesse botão primeiro e preencha na página que abrir. Só use e-mail + senha quando nada foi indicado ou quando ele mandou. Evite SMS, porque exige um código que o agente não tem. Um segredo do cofre pode valer só para um método; usá-lo no formulário errado dá "inválido" sem o segredo estar errado.
4. Digite o e-mail com `browser_type` como texto normal, ou como `§§secret(NOME)` se estiver no cofre. Digite a senha só como `§§secret(NOME_DO_SEGREDO)`, **e só na ref de um campo de senha**. A trava do navegador recusa segredo em qualquer outro campo (telefone, e-mail, nome) com "NÃO digitei §§secret(...)", e nada é digitado. Não contorne por `browser_console` nem por outra ref. Releia o `browser_snapshot` e use a ref do campo de senha, ou o dado certo para aquele campo. Nunca escreva a senha em claro nem a repita na resposta.
5. O cofre devolve o campo vazio e confirma "valor usado". Isso é normal. Só conclua que a senha falhou se o site disser isso.
6. Se o cofre mostrar outro nome de segredo no lugar do esperado, os dois têm o mesmo valor: o cofre exibe o nome do primeiro que bate. Não é erro.
7. Envie o formulário. Use primeiro as ações nativas: `browser_click` na ref do botão, ou `browser_press` "Enter" no campo. Só se elas não funcionarem, use `browser_console` com JS.
8. Depois de enviar, leia a página de novo com `browser_snapshot`. O login só vale quando a página saiu da tela de login (confira a URL e o conteúdo).

## Fluxo (o Matheus faz o login: "Resolver aqui")
Quando o pedido é mandar o botão "Resolver aqui" com o navegador aberto numa página de login para ELE entrar (conta dele, sem você digitar nada):
1. Abra (ou reabra) a URL e **confirme que a página carregou de verdade**: o `browser_snapshot` deve mostrar o formulário ou os botões de login. Uma página de erro ("Parece que algo deu errado"), em branco ou com spinner infinito NÃO está pronta para entregar.
2. Se vier erro ou página vazia, **recarregue você mesmo**. Espere 3–5 s (`terminal` com `sleep 5`) e chame `browser_navigate` de novo. Se persistir, tente outra abordagem, como abrir pela página inicial do site. Faça pelo menos 3 tentativas com abordagens diferentes antes de relatar falha. "Não digite nada nessa página" proíbe preencher campos, não proíbe recarregar ou reabrir.
3. Com a página de login visível, chame **`resolver_aqui`** com `pedido` (o que ele deve fazer, curto: "Entre na sua conta do iFood; o código chega no seu e-mail") e `aba` (o id da aba ou um pedaço do endereço; vazio = a da frente). Ela manda a ele no Telegram o print e o botão "🖥️ Resolver aqui", que abre essa aba no celular dele (link de 30 min). Se ela responder "NÃO FEITO", diga isso com clareza; não troque de canal por conta própria nem dê a tarefa por entregue.
4. Termine a sua resposta dizendo, em uma linha, o que ele precisa fazer e que você espera. Não digite nada, não clique em Entrar, não aceite termos.
5. Quando ele apertar "✅ Terminei", a conversa recebe o aviso: faça `browser_snapshot` (e `browser_vision` se precisar ver). Responda "entrou" se a página saiu da tela de login (cite qual página). Se não, diga o que apareceu (erro, 2FA, captcha, ainda no login) e, se for algo dele de novo, mande outro `resolver_aqui`.

## Se o navegador recusa o certificado ("Your connection is not private", ERR_CERT_*)
Não é erro transitório. Não é motivo para clicar em "Advanced" e prosseguir, nem para digitar senha. Mas também não pare na primeira tentativa. Diagnostique antes de pedir ajuda:
1. No `terminal`, rode `curl -vI https://HOST 2>&1 | grep -iE 'subject|issuer|subjectAltName|expire|SSL'` para ver para quais nomes o certificado vale e se expirou.
2. Procure o endereço exato do portal que o parceiro mandou. Veja o e-mail de aprovação no Gmail (só leitura, conector `mcp__google__`), e também fios, decisões e ficha. Tente esse endereço e as variações que o certificado cobre (com ou sem `www`, subdomínio).
3. Não use `web_search` para achar portal de parceiro: devolve lixo.
4. Se continuar recusando, pare e relate numa mensagem: host, erro exato, o que o certificado cobre e o que já tentou. Peça ao Matheus/operador a decisão. Não conclua sozinho que o site está inseguro sem esse diagnóstico.

## Armadilhas
- **Página de erro não é motivo para desistir na primeira leitura.** Erros de portais costumam ser transitórios: recarregue e reabra antes de avisar o Matheus.
- **Não troque o canal pedido por outro** (pediu Telegram, mandou WhatsApp). Se o canal não funciona, relate o bloqueio.
- Botões de portais modernos costumam ser `div`/`span` customizados. Um `.click()` por JS (`browser_console`) neles pode não disparar nada. Use `browser_click` na ref ou confira a tela com `browser_vision`.
- Se você repetiu a mesma ação com o mesmo resultado, mude de abordagem. Antes de digitar de novo num campo, releia o `browser_snapshot` e confira o valor do campo.
- Se o site responder "e-mail ou senha inválidos", confira se usou o método indicado (passo 3).
  - Se não usou, tente o método certo, uma vez.
  - Se já era o certo, faça no máximo uma nova tentativa e pare: repetir pode bloquear a conta.
- Você não vê o valor de um segredo. Não afirme de quem é um e-mail nem que o segredo "está errado" sem evidência. Diga só o que o site respondeu e qual método usou.
- Antes de desistir de um envio, tente `browser_click` e `browser_press` "Enter". Confira com `browser_vision` se a senha foi preenchida e se há erro escondido.
- Pare e chame o Matheus com `resolver_aqui` (print + botão para ele fazer na tela) só nestes casos. Captcha e "segure o botão" são sempre dele: nunca tente resolver você mesmo.
  - captcha;
  - código por SMS/e-mail;
  - 2FA;
  - senha recusada depois do método certo;
  - termos novos;
  - certificado recusado após o diagnóstico.

  Não peça para ele logar só porque um botão não respondeu (exceto quando o pedido já é entregar o login a ele).
- Depois de logar, siga a tarefa: não envie, não aceite termos, não crie nada e não anexe arquivos sem o OK dele (a menos que o pedido mande criar).
