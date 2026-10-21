# Moldes de vídeo e post (Raiz agora, NEXOS depois)

> **Regra do Matheus (14/10/2026): todo vídeo da Raiz Connect segue o kit de motion graphics da Raiz**, que mora no
> repositório erp-saas (branch `claude/integrar-instrucoes-ywizpw`): `.claude/skills/motion-graphics/SKILL.md`
> (etapas A–K), `marketing/brand-system.md` (logo, cores, Manrope + Instrument Serif, área segura, movimento, som,
> voz Carolina) e o modelo `marketing/_modelo-motion-html/`. Cada vídeo novo é um projeto em `marketing/<nome>/` lá.
> Os Reels desta pasta e os moldes deste repositório **não** valem mais para vídeo da Raiz (ficam como histórico e,
> no caso dos moldes, para outras marcas).


Objetivo: 30 moldes (versão 2, revisada por um avaliador cego em 13/10:
`calibracao/moldes/avaliacao_cega_2026-10-13.json`) de Reel, carrossel e story que servem para qualquer tipo de negócio. O agente escolhe o molde
que mais se adapta à situação, preenche uma ficha curta e a máquina gera o vídeo. A IA nunca escreve animação.

Fonte da verdade do catálogo: `infra/reels/moldes/catalogo.json` (é o que o agente consulta para escolher).
A tabela no fim deste arquivo sai dele.

## 1. Três camadas

| Camada | O que é | Quem mexe | Quando |
|---|---|---|---|
| Molde | animação pronta: cenas, efeitos, tempos, limites de cada campo | nós | uma vez por molde |
| Marca | logo (versão fundo escuro e fundo claro), cores, fonte, @, chamada padrão, voz e tom | cadastro do cliente | uma vez por negócio |
| Ficha | falas, números, produto, fotos | o agente | a cada post |

- Cada molde declara a ficha que aceita: campos, quantos itens, quantas letras cabem. Ficha fora do limite volta para
  o agente reescrever; nunca vai cortada para o vídeo.
- **Logo**: todo molde tem dois lugares fixos, marca d'água pequena logo abaixo da faixa do topo que o Instagram cobre
  (a partir de 240 px) e logo grande na cena final com o @ e a chamada. Aceita logo horizontal, quadrado ou só ícone; sem versão para o fundo, entra um selo atrás; sem logo, o
  nome da empresa na fonte da marca. Quem não tem logo (ou prefere) assina com uma **foto**: perfil, fachada, o
  dono ou um produto; ela entra redonda com o nome no topo e grande na cena final (`marca.foto`, `assinatura: foto`).
  Sem cores cadastradas, a paleta sai do próprio logo.
- **Estilos**: 5 linguagens visuais (vidro escuro, claro limpo, pop colorido, papel artesanal, noite neon) que
  qualquer molde aceita. Duas empresas no mesmo molde não ficam iguais: muda o estilo, a marca e o conteúdo.
- **Blocos**: os 30 moldes são montados com 13 blocos reaproveitáveis (título por palavra, número contando, lista,
  gráfico, chat, cartões, tela dividida, foto com zoom, filmagem, celular, carimbo, contagem, cena final). Construir
  um molde novo é combinar blocos, não começar do zero.

- **Mídia do próprio negócio primeiro**: em todo molde, o lugar de imagem de fundo aceita foto ou vídeo que o cliente
  mandar (a foto ganha zoom lento; o vídeo vira quadros com `motor/video_cliente.py`). O banco de filmagens feitas por IA
  é só reserva para quem não mandou nada.

## 2. Como o agente usa

1. Parte do objetivo (atrair, engajar, ensinar, vender, avisar) e do que o negócio tem (fotos, números, novidade).
2. Filtro pelo código: formato pedido, mídia disponível (sem fotos reais, nada de antes e depois ou depoimento),
   objetivo. Sobram 2 a 4 moldes.
3. A IA escolhe entre esses e preenche a ficha. Texto curto: um modelo barato basta.
4. **Conta pelo código**: lucro, desconto, economia do combo, soma das fatias, totais. A IA só dá os valores de
   entrada; o código calcula e confere.
5. Geração na máquina do agente (navegador sem tela + ffmpeg) e conferência automática:
   - texto cabe e nenhuma letra cortada (mede cada caixa de texto na página);
   - tela bate com a fala (cada cena só mostra o que a fala do momento diz);
   - contraste do texto e do logo;
   - nada na área que o Instagram cobre: Reel topo 220 px, rodapé 420 px, botões à direita 160 px; story topo 250 px,
     rodapé 340 px; carrossel 4:5 com o essencial no centro 3:4 (a grade do perfil corta as laterais);
   - duração dentro do limite do molde.
6. Vai para aprovação (AR Board na fase de calibração; depois amostra) e entra na agenda de publicação.
7. Nenhum molde serve: o agente registra um **pedido de molde novo** em vez de improvisar. A biblioteca cresce pelo
   que os clientes pedem de verdade.

## 3. Regras que valem para todos

- **Sem dado real, não gera.** Custo, preço "de", horário livre, número de marco, depoimento e fonte só com dado
  informado pelo dono ou tirado do sistema. Faltou: o agente troca de molde, nunca chuta.
- Preço "de" só se foi praticado; prazo de oferta real; nada de contagem que reinicia (Código de Defesa do Consumidor).
- Nenhum concorrente ou aplicativo citado pelo nome. Humor nunca debocha do cliente. Sem política, religião ou saúde
  sem fonte.
- Antes e depois em saúde e estética regulada só com confirmação de que o conselho da profissão permite.
- Filmagem realista feita por IA segue a regra de rótulo de IA do Instagram.
- Rodízio: nunca três moldes de humor (POV, expectativa, conversa) seguidos.

- Depoimento só de fala real, com a prova guardada (mensagem ou avaliação). Sem prova, o molde recusa.
- Número que choca só com fonte (nome e ano). Agenda aberta só com horários reais. Oferta só com prazo real.
- Conversa encenada (molde conversa no celular) com selo de cena encenada, sem nome nem foto de pessoa real e sem o
  visual do WhatsApp.
- Sem travessão nos textos (AR Board 13/10: "deixa com cara de IA"). Legendas sem emoji (decisão de 13/10).
- Músicas só CC0 do banco; fontes só livres (OFL); filmagens geradas por nós (Wan 2.2 com o token do Matheus ou
  AWS Nova Reel), com uso comercial permitido.

## 4. Custo por post

| Parte | Como | Custo |
|---|---|---|
| Ficha | modelo de IA barato, texto curto | centavos |
| Voz | Carolina, do Amazon Nova 2 Sonic (padrão de toda narração desde 14/10, pedido do Matheus): o roteiro vai no prompt e a transcrição do que ela disse é conferida palavra por palavra; leitura diferente é refeita, nunca usada (`motor/voz_sonic.mjs`, `npm ci` em `motor/`) | ~US$ 0,02 por Reel de 1 minuto |
| Filmagem | banco por ramo feito uma vez (Wan 2.2 grátis ou Nova Reel ~US$ 0,50 por trecho) e reaproveitado | zero no dia a dia |
| Geração | máquina do agente (já paga) | zero |
| Refação | conferência automática antes da aprovação | zero |

Abaixo de R$ 0,50 por post. Vídeo pronto por API (ex.: Luma Ray2 ~US$ 1,50 por segundo) ficaria em dezenas de reais
por Reel. Motor próprio (navegador + ffmpeg) em vez de Remotion, que pede licença paga para empresa.

## 5. Ondas

| Onda | Moldes | Por quê |
|---|---|---|
| 1 | POV, Expectativa x Realidade, Frases que você mais ouve, Quiz A, B ou C, Time A ou Time B, Mito ou verdade, A conta mudou, Custo escondido | já existem feitos à mão para a Raiz; viram moldes com ficha e geram a semana 2 |
| 2 | Isso ou aquilo, Oferta relâmpago, Vitrine do dia, Depoimento de cliente, Antes e depois, Como pedir, Data especial, Produto em destaque, Aviso | os mais usados por qualquer pequeno negócio (escolha do avaliador cego) e as datas do ano |
| 3 | Os tipos de cliente, Conversa no celular, Do começo ao fim, Passo a passo, Não faça x Faça, Demonstração no celular, Pergunta do cliente, Lançamento, Combo ou kit, Avalia ou indica | variedade para atrair, engajar e ensinar |
| 4 | Agenda aberta, Bastidores e história, Marco e agradecimento | institucional |
| 5 | Lançamento de app, Lançamento de produto, Inauguração, Manifesto de marca | comerciais de 1 minuto, narrados com música baixa por baixo (`musica_sob_voz`), um por modelo de negócio: digital, produto físico, ponto físico e serviço (pedido do Matheus em 14/10) |
| 6 | Oferta completa | a oferta 'Lucro na Mão em 30 Dias' (Hormozi, 14/10) não cabia em nenhum molde: oferta relâmpago pede preço 'de' e prazo, os lançamentos pedem 55 a 65 s e cenas de marca. Aguarda o AR Board |

Cada molde só entra no catálogo do agente depois de:
1. três fichas de teste de ramos diferentes (ex.: confeitaria, oficina, salão) geradas e passando na conferência;
2. aprovado pelo Matheus no AR Board (os comentários viram regra do molde e teste).

## 6. NEXOS

O motor e o catálogo nascem aqui, provados com a Raiz. No NEXOS entram por Story e pelas regras de lá (quem escreve
o código é a Main Opus): a escolha do molde é decisão semântica (proposta, nunca autoridade), a conta é do código,
publicar é efeito externo e passa pela ação governada, e nada vai a cliente real antes da ROS-F9-013. Esta sessão
entrega o motor, o catálogo e os testes prontos para a Story.

### Criador de vídeos do NEXOS (decidido com o Matheus em 21/10)

Uma página do NEXOS onde o dono do restaurante faz o próprio vídeo. Entra por Story, depois do MVP atual, como frente
de crescimento do cliente (não aumenta o primeiro piloto).

- **Quem e para quê:** o dono do restaurante, sozinho; vídeo vertical de 15 a 60 s para Instagram e WhatsApp. Anúncio
  pago e vídeo longo ficam fora da 1ª versão.
- **O que ele preenche:** logo e 2 cores (a Marca, guardada depois da 1ª vez), uma frase do que quer e, se quiser,
  fotos dos pratos; nome, endereço, WhatsApp e cardápio vêm do NEXOS.
- **Escolha:** a IA sugere 3 Moldes que combinam com a frase, mostrados como Prévia (imagem parada com a Marca dele,
  grátis); o vídeo, que gasta voz, só é gerado depois da escolha. Ele nunca vê o catálogo inteiro. Entram todos os
  Moldes do catálogo, menos os que o Matheus rejeitou no AR Board ("pode aprovar os outros, estão bons no geral").
- **Quando não se encaixa:** conteúdo que não cabe (texto longo, foto ruim, cor sem contraste) é ajustado pelo motor
  sozinho; pedido que nenhum Molde atende vira Pedido sem molde: a página diz o que não dá e oferece os 3 mais
  próximos. Nenhum Molde novo é criado na hora; a lista de Pedidos sem molde vira a fila do que construir.
- **Foto do prato:** só a do cliente (ajuste automático de recorte, luz e tamanho; se continuar ruim, pede outra). A
  IA nunca inventa foto do prato; no máximo fundo ou ambiente.
- **Voz e música:** Carolina por padrão ou "sem voz"; música só do banco livre de direitos do motor.
- **Conferência:** antes de mostrar, as conferências do motor e o Crítico; reprovou, refaz uma vez; reprovou de novo,
  oferece outro Molde. O cliente nunca vê vídeo reprovado.
- **Depois de pronto:** até 2 ajustes grátis (cada um gera um vídeo novo); só baixar na 1ª versão (publicar direto
  fica para depois). Biblioteca do restaurante guarda os vídeos por 90 dias; a Ficha fica para gerar de novo.
- **Limite e custo:** limite mensal de vídeos por plano (ex.: 10 no básico, 30 no profissional), sem avulso na 1ª
  versão; ajuste não conta. Custo por vídeo abaixo de US$ 0,15 (texto centavos, voz ~US$ 0,02, foto de fundo só se
  faltar US$ 0,04 a 0,06; render no próprio servidor).
- **Onde roda:** uma cópia do motor e do catálogo dentro do NEXOS, como peça própria; nunca dependendo do agente
  pessoal do Matheus.

## 7. Catálogo

| # | Molde | Grupo | Onda | Formatos | Situação | Diferencial | Já existe |
|---|---|---|---|---|---|---|---|
| 1 | POV (`pov`) | Atrair | 1 | reel | Situação engraçada do dia a dia do ramo para a pessoa se ver e mandar para um amigo. | Uma cena só, ritmo de meme; o texto é a piada. | r_pov |
| 2 | Expectativa x Realidade (`expectativa`) | Atrair | 1 | reel | Contraste bem-humorado entre o que o cliente imagina e o que é a rotina de quem faz. | Corte seco no meio; vive do contraste das duas imagens. | r_expec |
| 3 | Os tipos de cliente (`tipos-cliente`) | Atrair | 3 | carrossel, reel | Retrato divertido dos perfis de cliente que todo negócio tem. | Personagens: cada cartão é um perfil com ilustração própria. |  |
| 4 | Frases que você mais ouve (`frases`) | Atrair | 1 | carrossel, reel | Frases típicas que o dono escuta, numeradas, pedindo para comentar o número. Inclui o antigo 'coisas que só quem ___ entende'. | Balões de fala; puxa comentário com 'comenta o número'. | c_frases |
| 5 | Conversa no celular (`chat`) | Atrair | 3 | reel | Conversa encenada entre cliente e dono, com virada no fim (claramente encenada, sem nome real). | Tudo acontece dentro de um celular; som de notificação a cada mensagem. |  |
| 6 | Do começo ao fim (`processo`) | Atrair | 3 | reel | Mostra como o produto ou serviço é feito, em cortes rápidos. | Prende pela transformação; só com material real do negócio. |  |
| 7 | Quiz A, B ou C (`quiz`) | Engajar | 1 | carrossel, reel | Pergunta com três respostas para comentar; a resposta certa vem no fim e ensina algo. | Suspense até a última tela; a resposta é a aula. | c_quiz |
| 8 | Time A ou Time B (`time`) | Engajar | 1 | carrossel, reel | Tema que divide opinião no ramo para cada um defender o seu lado nos comentários. | Opinião, não dado: a tela dividida pede para escolher. | c_polemica |
| 9 | Mito ou verdade (`mito`) | Engajar | 1 | carrossel, reel | Crenças comuns do ramo, cada uma com carimbo MITO ou VERDADE e a explicação. | O carimbo que bate é o momento do vídeo. | c_mito |
| 10 | Isso ou aquilo (`escolha`) | Engajar | 2 | reel, story | Pares de produtos do próprio negócio para o cliente escolher; mostra o cardápio sem parecer anúncio. | Usa as fotos do cliente; vitrine disfarçada de brincadeira. |  |
| 11 | A conta mudou (`conta-mudou`) | Ensinar | 1 | reel | Um custo subiu e o preço não acompanhou: mostra o antes e o depois do lucro. Variante para o cliente final: 'por que o preço mudou'. | Gráfico de linha + antes x depois; todos os números saem da ficha pelo código. | 2_brigadeiro |
| 12 | Custo escondido (`custo-escondido`) | Ensinar | 1 | reel | Custos que o dono esquece de pôr no preço, somando até o total que some do bolso. | Iceberg: o visível em cima, o que pesa embaixo; total somado pelo código. | 3_salgado |
| 13 | Passo a passo (`passo-a-passo`) | Ensinar | 3 | reel, carrossel | Tutorial curto de algo útil para o cliente (ou para o dono). Modo 'lista para salvar' (prancheta com caixinhas, antigo checklist) quando não há ordem. | Linha do tempo vertical; salvamento. |  |
| 14 | Não faça x Faça (`faca-nao-faca`) | Ensinar | 3 | carrossel, reel | Erros comuns e o jeito certo, lado a lado. | Vermelho e verde lado a lado; leitura rápida. |  |
| 15 | Demonstração no celular (`demonstracao`) | Ensinar | 3 | reel | Mostra o app, site, cardápio digital ou ferramenta funcionando. | Moldura de celular com toques animados; mostra o produto de verdade. |  |
| 16 | Pergunta do cliente (`pergunta-cliente`) | Ensinar | 3 | reel, story, carrossel | Responde uma dúvida ou objeção frequente (entrega no bairro, aceita cartão, por que custa isso). | Uma pergunta por peça; quebra a objeção que trava a venda. |  |
| 17 | Oferta relâmpago (`oferta`) | Vender | 2 | reel, story | Promoção com preço e prazo. | Contagem regressiva; desconto calculado pelo código. |  |
| 18 | Lançamento (`lancamento`) | Vender | 3 | reel, story | Produto ou serviço novo revelado com suspense. | Revelação com suspense; carimbo NOVO. |  |
| 19 | Combo ou kit (`combo`) | Vender | 3 | reel, carrossel | Itens que se juntam num kit, com a economia em relação a comprar separado. | Itens se juntando numa caixa; economia calculada pelo código. |  |
| 20 | Vitrine do dia (`cardapio`) | Vender | 2 | story, reel, carrossel | O que tem hoje, com foto e preço, para decidir rápido. | Feito para o dia a dia; atualiza todo dia sem reescrever. |  |
| 21 | Depoimento de cliente (`depoimento`) | Vender | 2 | reel, carrossel, story | Fala real de um cliente, com permissão; nunca inventada. | Prova social; o sistema exige a origem da fala e bloqueia depoimento sem prova. |  |
| 22 | Antes e depois (`antes-depois`) | Vender | 2 | reel, carrossel | Resultado visual de um serviço: uma barra desliza revelando o depois. | Barra deslizante; só serve com fotos reais do cliente. |  |
| 23 | Como pedir (`como-pedir`) | Vender | 2 | reel, story, carrossel | Explica em 3 passos como comprar, agendar ou encomendar. Também mostra onde atende: bairros de entrega, endereço ou evento. | Ícones grandes; tira a dúvida que impede a compra. |  |
| 24 | Agenda aberta (`agenda`) | Vender | 4 | story | Mostra horários ou datas livres para quem vende por agendamento. | Calendário vivo; urgência sem mentir (só horários reais). |  |
| 25 | Data especial (`data-especial`) | Vender | 2 | reel, carrossel, story | Dia das Mães, Páscoa, Natal, Black Friday: o que o negócio oferece e até quando encomendar. | Calendário do ano: o agente sabe as datas e prepara antes. |  |
| 26 | Produto em destaque (`produto-semana`) | Vender | 2 | reel, carrossel, story | Destaca algo que já existe, sem promoção nem novidade. | Zoom nos detalhes; o post de todo dia sem precisar de motivo. |  |
| 27 | Avalia ou indica (`avalia-indica`) | Vender | 3 | story, reel | Pede avaliação no Google ou indicação, com benefício claro. | Transforma cliente satisfeito em divulgação. |  |
| 28 | Bastidores e história (`bastidores`) | Institucional | 4 | reel, carrossel | Quem faz, como faz e por que começou, com fotos do próprio negócio. Modo equipe: quem te atende (foto, nome, função, frase da pessoa, com permissão). | Fotos reais com zoom lento; aproxima o cliente do dono. |  |
| 29 | Aviso (`aviso`) | Institucional | 2 | story, reel | Horário especial, feriado, férias, mudança de endereço ou de telefone. | Claro e rápido; um cartaz animado que todo negócio precisa. |  |
| 30 | Marco e agradecimento (`marco`) | Institucional | 4 | reel, carrossel | Comemora um número ou data e agradece aos clientes. | Celebração; número real conferido. |  |
| 31 | Lançamento de app ou software (`lanca-app`) | Lançar | 5 | reel, story | Comercial de 1 minuto para lançar um app, sistema, plataforma ou curso online (negócio digital). | Zoom na tela: a câmera mergulha no ponto do print que importa, com contorno acendendo. |  |
| 32 | Lançamento de marca de produto (`lanca-produto`) | Lançar | 5 | reel, story | Comercial de 1 minuto para lançar uma marca ou linha de produto físico (varejo, e-commerce, indústria, artesanato). | Chamadas de detalhe com linha e ponto saindo do produto, posicionadas pelo código. |  |
| 33 | Inauguração (`inauguracao`) | Lançar | 5 | reel, story | Comercial de 1 minuto para a abertura de um ponto físico (restaurante, salão, oficina, clínica, loja de bairro). | Fita de inauguração cortada pela tesoura revelando a fachada. |  |
| 34 | Manifesto de marca (`manifesto`) | Lançar | 5 | reel | Comercial de 1 minuto para uma marca que nasce ou muda de identidade (serviço, B2B, agência, consultoria). | O logo se monta a partir das partes do próprio PNG. |  |
| 35 | Oferta completa (`oferta-completa`) | Vender | 6 | reel | A oferta inteira num Reel narrado: o resultado que a pessoa quer, o que entra com o valor de cada peça, o preço, a garantia e a vaga limitada de verdade. | O recibo que se monta peça por peça e soma o valor; o preço chega ao lado, nunca como preço 'de'. |  |

## 8. Detalhe de cada molde

### 1. POV (`pov`)

- **Quando usar:** Situação engraçada do dia a dia do ramo para a pessoa se ver e mandar para um amigo.
- **Formato:** reel · 13 a 15 s · voz: não (música) · mídia: filmagem do banco ou foto
- **Cenas:** frase 'POV: …' grande sobre a filmagem → virada com a reação (texto curto) → final
- **Ficha:** situacao (até 70 letras); virada (até 40 letras); musica (do banco CC0)
- **Exemplos:** Salgados: cliente pedindo precinho às 23h; Salão: cliente que mostra foto da atriz e pede igual; Oficina: 'só um barulhinho' que era o motor
- **Regras:** Aceitar uma foto ou vídeo do próprio cliente como fundo principal e deixar o banco de filmagens só como reserva. Tirar a virada quando a piada já fecha na primeira frase.

### 2. Expectativa x Realidade (`expectativa`)

- **Quando usar:** Contraste bem-humorado entre o que o cliente imagina e o que é a rotina de quem faz.
- **Formato:** reel · 14 a 16 s · voz: não (música) · mídia: 2 filmagens ou 2 fotos
- **Cenas:** EXPECTATIVA com imagem bonita → corte seco na batida → REALIDADE com a bagunça → final
- **Ficha:** expectativa (até 40 letras); realidade (até 40 letras); imagens (2)
- **Exemplos:** Confeitaria: bolo de vitrine x cozinha às 3h; Personal: treino de foto x aluno faltando; Restaurante: salão cheio x pia lotada
- **Regras:** Proibir sujeira e falta de higiene na imagem da realidade quando o ramo for comida, saúde ou estética. Permitir que a realidade seja só texto sobre fundo liso quando não houver uma segunda imagem boa.

### 3. Os tipos de cliente (`tipos-cliente`)

- **Quando usar:** Retrato divertido dos perfis de cliente que todo negócio tem.
- **Formato:** carrossel, reel · 24 s · voz: opcional · mídia: nenhuma (ícone grande de um conjunto fixo)
- **Cenas:** título 'Os N tipos de cliente de todo ___' → um cartão por tipo: nome + frase típica + ilustração → pergunta 'qual você é?' → final
- **Ficha:** ramo (até 30 letras); tipos (3 a 6: nome até 25 letras, frase até 60)
- **Exemplos:** Hamburgueria: o que tira tudo do lanche; Clínica de estética: a que já leu tudo no TikTok; Loja de roupa: o que prova 12 e leva 1
- **Regras:** Trocar a ilustração por um ícone grande de um conjunto fixo ou por um emoji. Proibir tipo que deboche do cliente, como o pão-duro ou o chato.

### 4. Frases que você mais ouve (`frases`)

- **Quando usar:** Frases típicas que o dono escuta, numeradas, pedindo para comentar o número. Inclui o antigo 'coisas que só quem ___ entende'.
- **Formato:** carrossel, reel · 29 a 35 s · voz: não · mídia: nenhuma
- **Cenas:** capa com a pergunta → uma frase por tela em balão de fala (no Reel, cartões trocando na batida) → fechamento com a mensagem do negócio → final
- **Ficha:** pergunta (até 60 letras); frases (5 a 8, até 70 letras cada); fechamento (até 120 letras)
- **Exemplos:** Salgadeira: 'faz por 50 o cento?'; Fotógrafo: 'é só tirar umas fotinhas'; Marmitaria: 'tem como mandar mais arroz?'
- **Regras:** Criar a versão Reel com cartões. Dar uma regra de tom: a frase pode ser engraçada, mas o fechamento não pode humilhar quem disse.

### 5. Conversa no celular (`chat`)

- **Quando usar:** Conversa encenada entre cliente e dono, com virada no fim (claramente encenada, sem nome real).
- **Formato:** reel · 14 s · voz: não (som de mensagem + música) · mídia: nenhuma
- **Cenas:** celular com a conversa → mensagens chegando com 'digitando…' → virada (resposta do dono ou do cliente) → final
- **Ficha:** mensagens (4 a 8 falas alternadas, até 80 letras cada); virada (até 60 letras)
- **Exemplos:** Confeitaria: bolo de 3 andares para amanhã; Mecânico: 'quanto fica?' sem dizer o carro; Delivery: 'já saiu?' 2 minutos depois do pedido
- **Regras:** Usar um chat genérico, sem o visual nem a marca do WhatsApp. Pôr um selo pequeno de cena encenada e mudar o nome do molde para Conversa no celular.

### 6. Do começo ao fim (`processo`)

- **Quando usar:** Mostra como o produto ou serviço é feito, em cortes rápidos.
- **Formato:** reel · 13 a 15 s · voz: não (música) · mídia: 4 a 6 fotos ou trechos do próprio cliente
- **Cenas:** cortes rápidos na batida, do começo ao resultado → legenda mínima → final
- **Ficha:** midias (4 a 6 do cliente, em ordem); legendas (opcionais, até 25 letras)
- **Exemplos:** Bolo do recheio à decoração; Carro da sujeira ao polimento; Corte de cabelo do antes ao acabamento

### 7. Quiz A, B ou C (`quiz`)

- **Quando usar:** Pergunta com três respostas para comentar; a resposta certa vem no fim e ensina algo.
- **Formato:** carrossel, reel · 21 a 46 s · voz: não · mídia: 1 foto opcional
- **Cenas:** pergunta com foto → opções A, B e C → 'comenta antes de passar' → resposta com a conta explicada → final
- **Ficha:** pergunta (até 80 letras); opcoes (3, até 20 letras); certa (A, B ou C); explicacao (até 140 letras (números conferidos pelo código)); numeros (valores da explicação em campos próprios (o código faz a conta))
- **Exemplos:** Confeitaria: preço mínimo do bolo; Academia: quantas calorias tem o açaí; Imobiliária: quanto custa o condomínio de verdade
- **Regras:** Pôr os números da explicação em campos próprios para o código fazer a conta. No Reel, incluir uma tela de 'pausa e responde' com a contagem antes da resposta. Proibir tema de saúde sem fonte, como calorias.

### 8. Time A ou Time B (`time`)

- **Quando usar:** Tema que divide opinião no ramo para cada um defender o seu lado nos comentários.
- **Formato:** carrossel, reel · 19 a 36 s · voz: não · mídia: 1 foto opcional
- **Cenas:** tela dividida: lado A x lado B → argumento de cada lado → 'comenta o seu time' → fechamento neutro do negócio
- **Ficha:** tema (até 60 letras); lado_a (até 30); lado_b (até 30); argumentos (1 por lado, até 80)
- **Exemplos:** Delivery: taxa à parte ou embutida; Pizzaria: borda recheada sim ou não; Salão: escova ou secar natural
- **Regras:** No Reel, aumentar para 10 a 12 s, porque em 8 s não dá para ler dois argumentos. Bloquear temas de política, religião e saúde.

### 9. Mito ou verdade (`mito`)

- **Quando usar:** Crenças comuns do ramo, cada uma com carimbo MITO ou VERDADE e a explicação.
- **Formato:** carrossel, reel · 32 a 44 s · voz: opcional · mídia: nenhuma
- **Cenas:** capa → afirmação → carimbo MITO/VERDADE batendo → explicação curta → repete por item → final
- **Ficha:** tema (até 50 letras); itens (3 a 5 no carrossel, até 3 no Reel: afirmação até 70, veredito, explicação até 120, fonte quando saúde, alimento ou dinheiro)
- **Exemplos:** Confeitaria: 'preço alto espanta cliente'; Clínica: 'protetor só no verão'; Mecânico: 'gasolina aditivada limpa o motor'
- **Regras:** Exigir fonte quando o tema for saúde, estética, alimento ou dinheiro. Limitar a 3 itens no Reel para não ficar longo.

### 10. Isso ou aquilo (`escolha`)

- **Quando usar:** Pares de produtos do próprio negócio para o cliente escolher; mostra o cardápio sem parecer anúncio.
- **Formato:** reel, story · 16 a 18 s · voz: não (música) · mídia: fotos dos produtos
- **Cenas:** título 'Escolhe um' → 3 a 5 pares de fotos lado a lado com 'ou' → 'conta nos comentários' → final
- **Ficha:** pares (3 a 5 pares de produtos (foto + nome até 25 letras))
- **Exemplos:** Doceria: brigadeiro ou beijinho; Lanchonete: coxinha ou kibe; Loja: tênis branco ou preto
- **Regras:** No story, deixar um espaço vazio para o dono colocar a enquete nativa, que o código não consegue criar. Exigir que as duas fotos de cada par tenham a mesma qualidade.

### 11. A conta mudou (`conta-mudou`)

- **Quando usar:** Um custo subiu e o preço não acompanhou: mostra o antes e o depois do lucro. Variante para o cliente final: 'por que o preço mudou'.
- **Formato:** reel · 25 a 33 s · voz: sim · mídia: filmagem do banco
- **Cenas:** gancho com o insumo que subiu → preço atual na etiqueta → gráfico do custo subindo → lucro antes x depois → efeito num lote (cento, mês) → frase de virada → final
- **Ficha:** produto (até 25 letras); insumo (até 25); preco (R$); custo_antes (R$); custo_hoje (R$); lote (quantidade (ex.: 100)); falas (6 a 8, geradas e conferidas)
- **Exemplos:** Brigadeiro e o leite condensado; Lava-jato e o produto de limpeza; Marmita e o arroz
- **Regras:** Marcar como molde para quem vende para outros negócios. Para o cliente final, criar a variante 'por que o preço mudou'. Bloquear a geração quando faltar custo real.

### 12. Custo escondido (`custo-escondido`)

- **Quando usar:** Custos que o dono esquece de pôr no preço, somando até o total que some do bolso.
- **Formato:** reel · 28 a 38 s · voz: sim · mídia: filmagem do banco
- **Cenas:** gancho: preço de venda → custo que todo mundo lembra → 'mas tem o que ninguém coloca' → iceberg: custos escondidos aparecendo embaixo d'água → total escondido → final → variante rosca: como cada R$ 100 se divide (antigo 'pra onde vai cada real')
- **Ficha:** produto (até 25); preco (R$); custo_visivel (R$); escondidos (3 a 6: nome até 25 + R$ real ou 'em média' marcado); falas (geradas)
- **Exemplos:** Cento de salgado: óleo, gás, embalagem, perdas; Corte de cabelo: produto, luz, toalha, comissão; Frete: pedágio, desgaste, tempo parado
- **Regras:** Absorver o pra-onde-vai como variante em rosca. Aceitar faixa ou estimativa marcada como 'em média' em vez de valor exato inventado.

### 13. Passo a passo (`passo-a-passo`)

- **Quando usar:** Tutorial curto de algo útil para o cliente (ou para o dono). Modo 'lista para salvar' (prancheta com caixinhas, antigo checklist) quando não há ordem.
- **Formato:** reel, carrossel · 33 a 40 s · voz: opcional · mídia: fotos ou filmagem opcional
- **Cenas:** promessa ('como fazer X em N passos') → linha do tempo vertical com cada passo acendendo → resultado → final
- **Ficha:** objetivo (até 60); passos (3 a 6, até 70 letras cada); resultado (até 60)
- **Exemplos:** Confeitaria: congelar bolo sem estragar; Pet shop: escovar o dente do cachorro; Contador: emitir nota como MEI
- **Regras:** Deixar a narração opcional, porque voz robótica em tutorial cansa. Absorver o checklist como modo sem ordem.

### 14. Não faça x Faça (`faca-nao-faca`)

- **Quando usar:** Erros comuns e o jeito certo, lado a lado.
- **Formato:** carrossel, reel · 29 a 45 s · voz: opcional · mídia: fotos opcionais
- **Cenas:** capa 'erros que custam caro' → par vermelho X / verde ✓ por erro → final
- **Ficha:** tema (até 50); pares (3 a 5: erro até 60 + certo até 60)
- **Exemplos:** Delivery: embalagem que vaza; Salão: lavar o cabelo depois da progressiva; Loja virtual: foto com fundo bagunçado
- **Regras:** Garantir que o erro e o certo de cada par sejam sobre a mesma coisa. Evitar que o erro pareça crítica direta a um cliente.

### 15. Demonstração no celular (`demonstracao`)

- **Quando usar:** Mostra o app, site, cardápio digital ou ferramenta funcionando.
- **Formato:** reel · 17 a 23 s · voz: sim · mídia: prints ou gravação da tela
- **Cenas:** problema → celular entrando na tela → toques e telas mudando → resultado → final
- **Ficha:** problema (até 60); telas (2 a 5 prints com legenda até 40); resultado (até 60)
- **Exemplos:** Raiz: calculadora de preço; Restaurante: pedir pelo cardápio digital; Clínica: agendar pelo link
- **Regras:** Aceitar gravação de tela real, além de prints. Para quem não tem ferramenta, o agente deve cair no como-pedir.

### 16. Pergunta do cliente (`pergunta-cliente`)

- **Quando usar:** Responde uma dúvida ou objeção frequente (entrega no bairro, aceita cartão, por que custa isso).
- **Formato:** reel, story, carrossel · 16 a 24 s · voz: opcional · mídia: nenhuma
- **Cenas:** a pergunta aparece como comentário recebido → resposta revelada → final
- **Ficha:** pergunta (até 90 letras (real, vinda de mensagem ou comentário)); resposta (até 160)
- **Exemplos:** Entrega no Cabula?; Faz bolo sem lactose?; Por que o orçamento é por avaliação?
- **Regras:** pergunta real; sem nome nem foto de quem perguntou

### 17. Oferta relâmpago (`oferta`)

- **Quando usar:** Promoção com preço e prazo.
- **Formato:** reel, story · 12 a 13 s · voz: opcional · mídia: foto do produto
- **Cenas:** produto entrando → preço antigo riscado → preço novo batendo → prazo com contagem → final com a chamada
- **Ficha:** produto (até 30); foto (1); preco_de (R$); preco_por (R$); ate (data/hora); condicao (até 60)
- **Exemplos:** Pizzaria: segunda em dobro; Loja: 20% até domingo; Estética: pacote de 3 sessões
- **Regras:** Exigir que o preço 'de' tenha sido praticado de verdade, com o dono confirmando. O prazo é obrigatório e o post não pode sair depois dele. Nada de contagem que reinicia.

### 18. Lançamento (`lancamento`)

- **Quando usar:** Produto ou serviço novo revelado com suspense.
- **Formato:** reel, story · 13 a 14 s · voz: opcional · mídia: 1 a 3 fotos
- **Cenas:** 'vem novidade' → revelação (cortina ou zoom) → nome + carimbo NOVO → 3 atributos → final
- **Ficha:** nome (até 30); fotos (1 a 3); atributos (3, até 30 letras); quando (opcional)
- **Exemplos:** Doceria: bolo de pote de pistache; Barbearia: corte + barba com toalha quente; Loja: coleção de verão
- **Regras:** Não esconder a foto principal por mais de 2 s, porque no Reel a pessoa pula. Permitir preço opcional na cena final.

### 19. Combo ou kit (`combo`)

- **Quando usar:** Itens que se juntam num kit, com a economia em relação a comprar separado.
- **Formato:** reel, carrossel · 17 a 18 s · voz: opcional · mídia: fotos dos itens
- **Cenas:** itens entrando um a um com preço → itens voando para dentro da caixa → preço do combo → 'economia de R$ X' → final
- **Ficha:** nome (até 30); itens (2 a 6: nome + preço avulso + foto); preco_combo (R$)
- **Exemplos:** Hamburgueria: combo família; Kit festa: bolo + 100 docinhos; Salão: dia da noiva
- **Regras:** Somar os preços avulsos pelo código e bloquear a peça se o combo não for mais barato. Aceitar uma foto só do kit montado quando não houver foto de cada item.

### 20. Vitrine do dia (`cardapio`)

- **Quando usar:** O que tem hoje, com foto e preço, para decidir rápido.
- **Formato:** story, reel, carrossel · 15 a 19 s · voz: não (música) · mídia: fotos dos produtos
- **Cenas:** 'hoje tem' → grade de produtos rolando com nome e preço → carimbo ESGOTADO onde faltar → como pedir → final
- **Ficha:** itens (4 a 6 por tela (até 3 telas): foto + nome até 25 + preço); esgotados (opcional); como_pedir (até 50)
- **Exemplos:** Marmitaria: pratos do dia; Padaria: fornada da tarde; Brechó: peças novas
- **Regras:** Limitar a 4 a 6 itens por tela e dividir em várias telas. Criar uma área livre própria para story. Mudar o nome para Vitrine do dia, para servir também a quem não vende comida.

### 21. Depoimento de cliente (`depoimento`)

- **Quando usar:** Fala real de um cliente, com permissão; nunca inventada.
- **Formato:** reel, carrossel, story · 15 a 18 s · voz: não · mídia: print ou foto (com permissão)
- **Cenas:** aspas grandes → citação revelada palavra por palavra → nota em estrelas → nome ou primeiro nome + bairro → final
- **Ficha:** citacao (até 160 letras, copiada de mensagem real); autor (primeiro nome); estrelas (só se a fonte tiver nota (ex.: Google)); prova (id da mensagem ou print guardado); permissao (registro da permissão do cliente)
- **Exemplos:** Confeitaria: avaliação do Google; Oficina: mensagem de agradecimento; Personal: aluno contando o resultado
- **Regras:** Mostrar estrelas só quando a fonte tiver nota, como o Google. Guardar a permissão do cliente junto da prova. Nunca editar o texto da fala.

### 22. Antes e depois (`antes-depois`)

- **Quando usar:** Resultado visual de um serviço: uma barra desliza revelando o depois.
- **Formato:** reel, carrossel · 11 a 12 s · voz: não (música) · mídia: 2 fotos do mesmo ângulo
- **Cenas:** foto ANTES → barra deslizando revela DEPOIS → nome do serviço + tempo → final
- **Ficha:** antes (foto); depois (foto); servico (até 30); detalhe (até 40)
- **Exemplos:** Salão: coloração; Estética automotiva: polimento; Reforma: banheiro
- **Regras:** Bloquear ou pedir confirmação para clínica, odontologia e estética regulada, conforme a regra do conselho profissional. Conferir que as duas fotos são do mesmo ângulo e não foram editadas.

### 23. Como pedir (`como-pedir`)

- **Quando usar:** Explica em 3 passos como comprar, agendar ou encomendar. Também mostra onde atende: bairros de entrega, endereço ou evento.
- **Formato:** reel, story, carrossel · 13 a 18 s · voz: opcional · mídia: nenhuma
- **Cenas:** 'é fácil pedir' → 3 passos com ícones grandes → canal (link, WhatsApp, endereço) em destaque → final
- **Ficha:** passos (3, até 40 letras); canal (link, número ou endereço); prazo (opcional); pagamento (opcional); area_entrega (bairros ou raio, opcional); endereco (opcional (antigo 'onde estamos'))
- **Exemplos:** Encomenda de bolo com 3 dias; Agendamento de banho e tosa; Pedido de marmita da semana
- **Regras:** Incluir as formas de pagamento e a área de entrega como campos opcionais.

### 24. Agenda aberta (`agenda`)

- **Quando usar:** Mostra horários ou datas livres para quem vende por agendamento.
- **Formato:** story · 15 a 20 s · voz: não · mídia: nenhuma
- **Cenas:** calendário da semana → horários livres acendendo, ocupados riscados → 'garanta o seu' → final
- **Ficha:** periodo (semana ou mês); livres (lista de datas/horas); como_agendar (até 50)
- **Exemplos:** Salão: sábado com 2 vagas; Fotógrafo: datas de dezembro; Clínica: avaliações da semana
- **Regras:** Fazer só em story. Os horários devem vir da agenda real ou de confirmação do dono no dia, nunca de um preenchimento antigo.

### 25. Data especial (`data-especial`)

- **Quando usar:** Dia das Mães, Páscoa, Natal, Black Friday: o que o negócio oferece e até quando encomendar.
- **Formato:** reel, carrossel, story · 17 a 19 s · voz: opcional · mídia: 2 ou 3 fotos
- **Cenas:** tema da data com o visual da época → 2 ou 3 produtos ou serviços → prazo para encomendar contado pelo código → como pedir → final
- **Ficha:** data (da lista de datas do ano); itens (2 ou 3: foto + nome + preço opcional); prazo (data real de encomenda)
- **Exemplos:** Confeitaria: ovos de Páscoa até 5/4; Floricultura: Dia das Mães; Barbearia: Dia dos Pais com combo
- **Regras:** prazo real; o post não sai depois dele

### 26. Produto em destaque (`produto-semana`)

- **Quando usar:** Destaca algo que já existe, sem promoção nem novidade.
- **Formato:** reel, carrossel, story · 13 a 15 s · voz: opcional · mídia: 1 a 3 fotos
- **Cenas:** foto com zoom nos detalhes → 3 atributos → preço opcional → chamada → final
- **Ficha:** nome (até 30); fotos (1 a 3); atributos (3, até 30 letras); preco (opcional)
- **Exemplos:** Doceria: torta de limão; Pet shop: banho com hidratação; Loja: bolsa de couro

### 27. Avalia ou indica (`avalia-indica`)

- **Quando usar:** Pede avaliação no Google ou indicação, com benefício claro.
- **Formato:** story, reel · 20 a 22 s · voz: não · mídia: nenhuma
- **Cenas:** o pedido → o benefício → 3 passos → link ou código → final
- **Ficha:** tipo (avaliação ou indicação); beneficio (até 60 (regra clara do prêmio)); passos (3, até 40); link (link real)
- **Exemplos:** Avalia no Google e ganha um brigadeiro; Indica uma amiga e as duas ganham 10%; Avalie a oficina e concorra a uma lavagem
- **Regras:** benefício real e cumprido; sem comprar avaliação positiva (o benefício vale para qualquer nota)

### 28. Bastidores e história (`bastidores`)

- **Quando usar:** Quem faz, como faz e por que começou, com fotos do próprio negócio. Modo equipe: quem te atende (foto, nome, função, frase da pessoa, com permissão).
- **Formato:** reel, carrossel · 20 a 32 s · voz: opcional · mídia: 3 a 8 fotos do cliente
- **Cenas:** foto do dono com o nome → fotos com zoom lento e legendas curtas (3 atos: começo, hoje, amanhã) → final
- **Ficha:** fotos (4 a 8 com legenda até 50); atos (3 frases tiradas de uma entrevista curta com o dono, nunca inventadas)
- **Exemplos:** Confeitaria que começou na cozinha de casa; Oficina de pai para filho; Loja que nasceu no Instagram
- **Regras:** Aceitar a partir de 3 fotos. Os 3 atos devem vir de uma entrevista curta com o dono, nunca de uma história inventada pela IA.

### 29. Aviso (`aviso`)

- **Quando usar:** Horário especial, feriado, férias, mudança de endereço ou de telefone.
- **Formato:** story, reel · 12 a 20 s · voz: não · mídia: nenhuma
- **Cenas:** ícone do tipo de aviso → data em destaque → o que muda → final
- **Ficha:** tipo (feriado, férias, horário, endereço, telefone, falta de produto, agenda cheia, vaga de emprego); data (data (dia da semana calculado pelo código)); texto (até 100); volta (opcional); vaga (se vaga: função, 3 requisitos, como se candidatar, prazo)
- **Exemplos:** Fechado no feriado de 15/11; Novo endereço a partir de segunda; Horário estendido no Natal
- **Regras:** Pôr a data e o dia da semana calculados pelo código. Incluir o tipo 'falta de produto' ou 'agenda cheia'.

### 30. Marco e agradecimento (`marco`)

- **Quando usar:** Comemora um número ou data e agradece aos clientes.
- **Formato:** reel, carrossel · 13 a 14 s · voz: opcional · mídia: 1 foto opcional
- **Cenas:** número contando até o marco → confete → obrigado + foto → final
- **Ficha:** numero (valor real); o_que (até 40 (pedidos, anos, clientes)); obrigado (até 100)
- **Exemplos:** 1.000 bolos entregues; 5 anos de oficina; 10 mil seguidores
- **Regras:** Pedir a origem do número, como sistema ou contagem do dono. Proibir arredondar para cima.

### 35. Oferta completa (`oferta-completa`)

- **Quando usar:** A oferta inteira num Reel narrado: o resultado que a pessoa quer, o que entra com o valor de cada peça, o preço, a garantia e a vaga limitada de verdade.
- **Formato:** reel · 35 a 55 s · voz: sim (música baixa por baixo) · mídia: foto opcional do negócio na abertura
- **Cenas:** resultado com destaque → nome da oferta → uma peça por fala, entrando no recibo com o valor → total somado pelo código → preço ao lado do valor e condições → garantia carimbada (opcional) → vagas reais em casinhas (opcional) → final
- **Ficha:** resultado (até 90 letras); itens (3 a 6: nome até 30, detalhe, valor real ou incluso); preco (R$ real); condicoes (até 3); garantia (opcional, real); vagas (opcional, real)
- **Exemplos:** Raiz: Lucro na Mão em 30 Dias; Oficina: plano mensal de frota; Salão: Dia da Noiva
- **Regras:** O total é somado pelo código e o preço precisa ser menor que ele. Valor, preço, garantia e vagas só com origem. Sem preço 'de' riscado, sem prazo inventado, sem 'restam X vagas'.
