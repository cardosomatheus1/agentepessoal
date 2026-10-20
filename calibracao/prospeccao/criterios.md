# Critérios do Matheus para a prospecção (AR Board)

Rodada `prosp-2026-10-13-textos`: 13 textos reais de 10 a 12/10, julgados em 13/10. 11 aprovados, 2 rejeitados.

## Regras

1. **Sem travessão (— ou –): deixa com cara de IA.** Vale para todo texto do agente. Já está no código
   (`validar_texto`, `TRAVESSAO`) e no playbook (seção 3).
   [prosp-2026-10-13-textos/496712, 577081, 03c097, 628a59, 8bdec8]
2. **Comentário de aquecimento bom cita algo concreto do post** (o kit de 5 refeições, as sobremesas fit, o
   rondelli, a vitrine de tortinhas) e pergunta sobre aquilo. Os 4 aprovados fazem isso.
   [f05278, c7a159, adcdad, 84e5c4]
3. **As duas variantes da 1ª mensagem estão aprovadas no conteúdo** (A: como precifica; B: oferece a calculadora),
   inclusive a versão curta da A. [496712, 577081, 8bdec8, 628a59, 03c097]
4. **Resposta a quem respondeu com a calculadora está aprovada** no formato atual. [5cb0d3, ff0088]

## Dúvidas para o Matheus

- **Link já na 1ª mensagem.** Em 5 comentários ele pediu "já mandar o link". Hoje o código proíbe link na 1ª
  mensagem (decisão anterior: link só na resposta a quem escreveu, para proteger a conta de bloqueio por spam).
  Não mudado até ele confirmar.
- **Os 2 comentários rejeitados vieram sem comentário.** Hipótese: são genéricos, não citam um produto do post
  ("Quentinha de comida caseira é daquelas que sempre resolve", "Qual prato esgotou primeiro?").
  [5cfec0, ec5e8c]

---

Rodada `prospeccao-raiz-2026-10-20-mensagens-reais`: 11 mensagens que saíram de verdade (15 a 20/10), julgadas em
20/10. 6 aprovadas, 5 rejeitadas. Comentário geral dele: "em vez de oferecer só a planilha, quando vir o gancho falar
do software; quando vir que a empresa usa iFood, citar a integração, entre outras coisas; parar de pegar algo que viu
no perfil e oferecer planilha logo depois, fica bem sem nexo".

## Regras novas

5. **Nexo entre o gancho e o que se oferece.** O que a mensagem cita do perfil tem de levar, numa linha de
   raciocínio, ao que ela oferece ou pergunta. Detalhe solto ("vi o cardápio novo", "vi a pergunta sobre marinar")
   seguido da calculadora é "sem nexo". [prospeccao-raiz-2026-10-20-mensagens-reais/7f65cb, a66b4c, 0b798d; comentário geral]
6. **Oferecer o que combina com o gancho, não sempre a planilha.** Usa iFood → o Raiz Connect importa e concilia os
   arquivos do iFood e mostra o que sobra depois da taxa; encomenda/produção programada → produção que baixa os
   insumos e estoque; cardápio novo → custo e preço de cada prato novo; kit/combo → quanto sobra no kit; revenda/atacado
   → tabela de atacado x varejo. A calculadora fica para quando o gancho é preço ou custo. [comentário geral; 7f65cb]
7. **Citar a bio entre aspas soa como IA.** Diga com as próprias palavras o que viu. [32f7fe]
8. **Gancho de pedido/venda + pergunta de preço tem nexo e está aprovado.** [204d61, d6856a]
9. **Comentário de aquecimento curto sobre o cardápio da semana está aprovado** (o 5cfec0 rejeitado em 13/10 foi
   aprovado agora: vale o mais recente). [5cfec0, adcdad]

10. **A quem disse "agora não", deixar o link curto da calculadora está aprovado** (a rejeição do d367be foi só porque
    saiu duplicada no Direct, erro de envio já corrigido). [d367be]
