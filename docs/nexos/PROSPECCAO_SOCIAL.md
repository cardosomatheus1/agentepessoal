# Prospecção por interação no Instagram (NEXOS) — decidido com o Matheus em 21/10/2026

Segunda ideia dele para o NEXOS (grilling, 16 perguntas fechadas). Duas peças: a **rotina de aproximação** (seguir,
curtir, comentar, direct) e o **banco de leads por interação** (quem comenta nos concorrentes, com nota). Entra por
Story, depois do MVP, na frente de crescimento do cliente, **depois do Criador de vídeos** e só se o teste na Raiz
(abaixo) render.

## Decisões

| # | Decisão |
|---|---|
| Q1 | Para qualquer negócio (não só restaurante). |
| Q2 | Modo **assistido**: o NEXOS acha, dá nota, explica e escreve; o cliente executa cada ação no celular com 1 toque. Robô que segue/curte/manda direct sozinho viola as regras do Instagram e arrisca a conta do cliente; automático total só no futuro, como opção avançada, por decisão do Matheus. |
| Q3 | Só Instagram na 1ª versão. |
| Q4 | Comentário vale mais que curtida; dor ou pergunta de compra vale mais que elogio; curtida sozinha não entra; perfil fechado sem comentário não entra. |
| Q5 | Guarda só o público e necessário (@, comentário, data, post, nota) por 90 dias; quem pede para sair vai para a lista de não contatar (a global do NEXOS), para sempre. |
| Q6 | Vende para empresas ou para pessoas, as duas têm seguir e curtir; **direct só para quem demonstrou interesse na empresa**: seguiu de volta, curtiu ou comentou algo dela. |
| Q7 | Concorrentes vêm do módulo do NEXOS que já levanta concorrentes; o cliente pode acrescentar. Configuração: Instagram dele, concorrentes, cliente ideal numa frase, região. |
| Q8 | Nota 0 a 100 sempre com o motivo escrito (combina com o cliente ideal, intenção do comentário, recência, região). A conta é do código; a IA só propõe intenção e tipo de negócio. |
| Q9 | Cota mensal de comentários lidos por plano (custo ~US$ 2,60 por mil no Apify; 3 mil ≈ US$ 8); para quando a cota acaba, sem cobrança surpresa. |
| Q10 | Nomes do NEXOS: o @ é **identidade externa** (não Pessoa); o comentário/curtida é **Sinal**; com nota vira **Lead** (o canônico do NEXOS); quando responde, **Oportunidade**; cada ação é **ponto de contato**. |
| Q11 | **Critérios fixos**, definidos pelo produto; o cliente não cria métrica nova ("senão vai sair do padrão do programa"). |
| Q12 | Tetos provados na Raiz como padrão: 15 perfis/dia para seguir e curtir, direct começando em 5/dia subindo até 12, até 30 comentários/dia; o cliente baixa, não sobe; bloqueio do Instagram pausa a fila 48 h e avisa. |
| Q13 | Em cada perfil da Fila do dia, "comentar? sim/não"; comentário escrito pela IA citando algo concreto do post, com as regras do AR Board da Raiz (`calibracao/prospeccao/criterios.md`); "sim" por padrão quando o post tem até 7 dias e assunto que combina. |
| Q14 | Funil por concorrente e por fonte (achados, aproximados, interagiram, responderam, oportunidade); concorrente que não rende em 30 dias é sugerido para sair. |
| Q15 | **Antes de virar Story**: testar 2 semanas na Raiz a busca de quem comenta em 3 a 5 concorrentes do Raiz Connect, dentro dos US$ 5/mês do Apify; vira Story só se render lead melhor que a busca atual. |
| Q16 | Ordem no NEXOS: Criador de vídeos primeiro, depois esta, já com o número do teste. |

## Base que já existe

- Rotina da Raiz (limites, estados, nota 0 a 100, revisor dos textos): `docs/ARQUITETURA_PROSPECCAO.md`,
  `infra/vm/plugins/prospeccao/`. Resultado de 28 dias: leads achados pelo Instagram 13 aproximados, 2 responderam
  (~15%); planilha 0 respostas e 73% descartados (`docs/ESTUDO_FONTES_2026-10-12.md`).
- NEXOS já planeja: `ROS-F3-002` identidade externa, `ROS-F3-004` Lead canônico, `ROS-F3-005` Oportunidade,
  `ROS-F3-007` ponto de contato, `ROS-F6-007` não contatar global, `ROS-F8-012` roteamento de lead.

## Testes reais (21/10)

- **Empresa para empresa (Raiz, quem comenta na Saipos e na Anota AI):** 6 posts, 26 comentários, 20 perfis, 1 lead
  (@zegrillitauna, achado pelo perfil pessoal do dono que comentou; a IA leu o @ do negócio na bio). A maioria dos
  negócios de comida achados foi recusada por não ter cidade no perfil. Custo US$ 0,14.
- **Cliente final (exemplo: hamburgueria em Salvador, quem comenta em 3 hamburguerias):** 9 posts, 29 comentários,
  12 com intenção de compra (41%: "vcs estão funcionando?", "tem no ifood?", "hoje deu vontade"); uma das
  concorrentes parece ter fechado e os clientes dela procuram onde comer. Custo US$ 0,19. Somente leitura, nenhum dado
  guardado. Lições: filtro de cidade dos concorrentes é obrigatório (veio um Burger King de El Salvador); repetir com
  2 ou 3 ramos antes de prometer números.
- **IA liberada (Matheus, 21/10: "Tanto pro video como pra esse pode usar agente/llm"):** ler perfil e comentário
  (ramo, cidade, intenção, negócio do dono) e escrever textos; a nota e os limites continuam no código.
