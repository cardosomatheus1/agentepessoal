# Moldes de vídeo e post (Raiz agora, NEXOS depois)

Objetivo: 30 moldes de Reel, carrossel e story que servem para qualquer tipo de negócio. O agente escolhe o molde
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
- **Logo**: todo molde tem dois lugares fixos, marca d'água pequena no topo e logo grande na cena final com o @ e a
  chamada. Aceita logo horizontal, quadrado ou só ícone; sem versão para o fundo, entra um selo atrás; sem logo, o
  nome da empresa na fonte da marca. Sem cores cadastradas, a paleta sai do próprio logo.
- **Estilos**: 5 linguagens visuais (vidro escuro, claro limpo, pop colorido, papel artesanal, noite neon) que
  qualquer molde aceita. Duas empresas no mesmo molde não ficam iguais: muda o estilo, a marca e o conteúdo.
- **Blocos**: os 30 moldes são montados com 13 blocos reaproveitáveis (título por palavra, número contando, lista,
  gráfico, chat, cartões, tela dividida, foto com zoom, filmagem, celular, carimbo, contagem, cena final). Construir
  um molde novo é combinar blocos, não começar do zero.

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
   - nada na área que o Instagram cobre (topo 220 px, rodapé 420 px, faixa dos botões à direita 160 px);
   - duração dentro do limite do molde.
6. Vai para aprovação (AR Board na fase de calibração; depois amostra) e entra na agenda de publicação.
7. Nenhum molde serve: o agente registra um **pedido de molde novo** em vez de improvisar. A biblioteca cresce pelo
   que os clientes pedem de verdade.

## 3. Regras que valem para todos

- Depoimento só de fala real, com a prova guardada (mensagem ou avaliação). Sem prova, o molde recusa.
- Número que choca só com fonte (nome e ano). Agenda aberta só com horários reais. Oferta só com prazo real.
- Conversa encenada (molde chat) sem nome nem foto de pessoa real.
- Sem travessão nos textos (AR Board 13/10: "deixa com cara de IA"). Legendas sem emoji (decisão de 13/10).
- Músicas só CC0 do banco; fontes só livres (OFL); filmagens geradas por nós (Wan 2.2 com o token do Matheus ou
  AWS Nova Reel), com uso comercial permitido.

## 4. Custo por post

| Parte | Como | Custo |
|---|---|---|
| Ficha | modelo de IA barato, texto curto | centavos |
| Voz | AWS Polly | ~US$ 0,01 por Reel narrado |
| Filmagem | banco por ramo feito uma vez (Wan 2.2 grátis ou Nova Reel ~US$ 0,50 por trecho) e reaproveitado | zero no dia a dia |
| Geração | máquina do agente (já paga) | zero |
| Refação | conferência automática antes da aprovação | zero |

Abaixo de R$ 0,50 por post. Vídeo pronto por API (ex.: Luma Ray2 ~US$ 1,50 por segundo) ficaria em dezenas de reais
por Reel. Motor próprio (navegador + ffmpeg) em vez de Remotion, que pede licença paga para empresa.

## 5. Ondas

| Onda | Moldes | Por quê |
|---|---|---|
| 1 | pov, expectativa, frases, quiz, time, mito, conta-mudou, custo-escondido | já existem feitos à mão para a Raiz; viram moldes com ficha e passam a gerar a semana 2 |
| 2 | oferta, lançamento, combo, cardápio, depoimento, antes e depois, como pedir, demonstração | vender: o que os clientes do NEXOS mais vão usar |
| 3 | só quem entende, tipos de cliente, chat, isso ou aquilo, pra onde vai cada real, passo a passo, não faça x faça, número | engajar e ensinar com variedade |
| 4 | checklist, tabela, agenda aberta, bastidores, aviso, marco | institucional e utilitário |

Cada molde só entra no catálogo do agente depois de:
1. três fichas de teste de ramos diferentes (ex.: confeitaria, oficina, salão) geradas e passando na conferência;
2. aprovado pelo Matheus no AR Board (os comentários viram regra do molde e teste).

## 6. NEXOS

O motor e o catálogo nascem aqui, provados com a Raiz. No NEXOS entram por Story e pelas regras de lá (quem escreve
o código é a Main Opus): a escolha do molde é decisão semântica (proposta, nunca autoridade), a conta é do código,
publicar é efeito externo e passa pela ação governada, e nada vai a cliente real antes da ROS-F9-013. Esta sessão
entrega o motor, o catálogo e os testes prontos para a Story.

## 7. Catálogo
| # | Molde | Grupo | Onda | Formatos | Situação | Diferencial | Já existe |
|---|---|---|---|---|---|---|---|
| 1 | POV (`pov`) | Atrair | 1 | reel | Situação engraçada do dia a dia do ramo para a pessoa se ver e mandar para um amigo. | Uma cena só, ritmo de meme; o texto é a piada. | r_pov |
| 2 | Expectativa x Realidade (`expectativa`) | Atrair | 1 | reel | Contraste bem-humorado entre o que o cliente imagina e o que é a rotina de quem faz. | Corte seco no meio; vive do contraste das duas imagens. | r_expec |
| 3 | Coisas que só quem ___ entende (`so-quem`) | Atrair | 3 | reel, carrossel | Lista rápida de verdades do ramo que geram identificação e marcações. | Cartões trocando no ritmo da música, sem narração. |  |
| 4 | Os tipos de cliente (`tipos-cliente`) | Atrair | 3 | carrossel, reel | Retrato divertido dos perfis de cliente que todo negócio tem. | Personagens: cada cartão é um perfil com ilustração própria. |  |
| 5 | Frases que você mais ouve (`frases`) | Atrair | 1 | carrossel | Frases típicas que o dono escuta, numeradas, pedindo para comentar o número. | Balões de fala; puxa comentário com 'comenta o número'. | c_frases |
| 6 | Conversa no WhatsApp (`chat`) | Atrair | 3 | reel | Conversa encenada entre cliente e dono, com virada no fim (claramente encenada, sem nome real). | Tudo acontece dentro de um celular; som de notificação a cada mensagem. |  |
| 7 | Quiz A, B ou C (`quiz`) | Engajar | 1 | carrossel, reel | Pergunta com três respostas para comentar; a resposta certa vem no fim e ensina algo. | Suspense até a última tela; a resposta é a aula. | c_quiz |
| 8 | Time A ou Time B (`time`) | Engajar | 1 | carrossel, reel | Tema que divide opinião no ramo para cada um defender o seu lado nos comentários. | Opinião, não dado: a tela dividida pede para escolher. | c_polemica |
| 9 | Mito ou verdade (`mito`) | Engajar | 1 | carrossel, reel | Crenças comuns do ramo, cada uma com carimbo MITO ou VERDADE e a explicação. | O carimbo que bate é o momento do vídeo. | c_mito |
| 10 | Isso ou aquilo (`escolha`) | Engajar | 3 | reel, story | Pares de produtos do próprio negócio para o cliente escolher; mostra o cardápio sem parecer anúncio. | Usa as fotos do cliente; vitrine disfarçada de brincadeira. |  |
| 11 | A conta mudou (`conta-mudou`) | Ensinar | 1 | reel | Um custo subiu e o preço não acompanhou: mostra o antes e o depois do lucro. | Gráfico de linha + antes x depois; todos os números saem da ficha pelo código. | 2_brigadeiro |
| 12 | Custo escondido (`custo-escondido`) | Ensinar | 1 | reel | Custos que o dono esquece de pôr no preço, somando até o total que some do bolso. | Iceberg: o visível em cima, o que pesa embaixo; total somado pelo código. | 3_salgado |
| 13 | Pra onde vai cada real (`pra-onde-vai`) | Ensinar | 3 | reel, carrossel | Explica o preço mostrando como cada R$ 100 (ou cada venda) se divide. | Gráfico de rosca; transparência que justifica preço. |  |
| 14 | Passo a passo (`passo-a-passo`) | Ensinar | 3 | reel, carrossel | Tutorial curto de algo útil para o cliente (ou para o dono). | Linha do tempo vertical; salvamento. |  |
| 15 | Não faça x Faça (`faca-nao-faca`) | Ensinar | 3 | carrossel, reel | Erros comuns e o jeito certo, lado a lado. | Vermelho e verde lado a lado; leitura rápida. |  |
| 16 | Número que choca (`numero`) | Ensinar | 3 | reel, story | Um dado forte com fonte, explicado em 3 frases. | Um número só ocupa a tela; sem fonte não sai. |  |
| 17 | Checklist (`checklist`) | Ensinar | 4 | carrossel, story | Lista de conferência que o cliente salva para usar depois. | Feito para salvar: prancheta com caixinhas. |  |
| 18 | Comparativo em tabela (`tabela`) | Ensinar | 4 | carrossel, reel | Compara duas ou três opções com dados, linha a linha. | Dado, não opinião (diferente do Time A ou B). |  |
| 19 | Demonstração no celular (`demonstracao`) | Ensinar | 2 | reel | Mostra o app, site, cardápio digital ou ferramenta funcionando. | Moldura de celular com toques animados; mostra o produto de verdade. |  |
| 20 | Oferta relâmpago (`oferta`) | Vender | 2 | reel, story | Promoção com preço e prazo. | Contagem regressiva; desconto calculado pelo código. |  |
| 21 | Lançamento (`lancamento`) | Vender | 2 | reel, story | Produto ou serviço novo revelado com suspense. | Revelação com suspense; carimbo NOVO. |  |
| 22 | Combo ou kit (`combo`) | Vender | 2 | reel, carrossel | Itens que se juntam num kit, com a economia em relação a comprar separado. | Itens se juntando numa caixa; economia calculada pelo código. |  |
| 23 | Cardápio ou catálogo do dia (`cardapio`) | Vender | 2 | story, reel, carrossel | O que tem hoje, com foto e preço, para decidir rápido. | Feito para o dia a dia; atualiza todo dia sem reescrever. |  |
| 24 | Depoimento de cliente (`depoimento`) | Vender | 2 | reel, carrossel, story | Fala real de um cliente, com permissão; nunca inventada. | Prova social; o sistema exige a origem da fala e bloqueia depoimento sem prova. |  |
| 25 | Antes e depois (`antes-depois`) | Vender | 2 | reel, carrossel | Resultado visual de um serviço: uma barra desliza revelando o depois. | Barra deslizante; só serve com fotos reais do cliente. |  |
| 26 | Como pedir (`como-pedir`) | Vender | 2 | reel, story, carrossel | Explica em 3 passos como comprar, agendar ou encomendar. | Ícones grandes; tira a dúvida que impede a compra. |  |
| 27 | Agenda aberta (`agenda`) | Vender | 4 | story, reel | Mostra horários ou datas livres para quem vende por agendamento. | Calendário vivo; urgência sem mentir (só horários reais). |  |
| 28 | Bastidores e história (`bastidores`) | Institucional | 4 | reel, carrossel | Quem faz, como faz e por que começou, com fotos do próprio negócio. | Fotos reais com zoom lento; aproxima o cliente do dono. |  |
| 29 | Aviso (`aviso`) | Institucional | 4 | story, reel | Horário especial, feriado, férias, mudança de endereço ou de telefone. | Claro e rápido; um cartaz animado que todo negócio precisa. |  |
| 30 | Marco e agradecimento (`marco`) | Institucional | 4 | reel, carrossel | Comemora um número ou data e agradece aos clientes. | Celebração; número real conferido. |  |

## 8. Detalhe de cada molde

### 1. POV (`pov`)

- **Quando usar:** Situação engraçada do dia a dia do ramo para a pessoa se ver e mandar para um amigo.
- **Formato:** reel · 7 a 12 s · voz: não (música) · mídia: filmagem do banco ou foto
- **Cenas:** frase 'POV: …' grande sobre a filmagem → virada com a reação (texto curto) → final
- **Ficha:** situacao (até 70 letras); virada (até 40 letras); musica (do banco CC0)
- **Exemplos:** Salgados: cliente pedindo precinho às 23h; Salão: cliente que mostra foto da atriz e pede igual; Oficina: 'só um barulhinho' que era o motor

### 2. Expectativa x Realidade (`expectativa`)

- **Quando usar:** Contraste bem-humorado entre o que o cliente imagina e o que é a rotina de quem faz.
- **Formato:** reel · 8 a 12 s · voz: não (música) · mídia: 2 filmagens ou 2 fotos
- **Cenas:** EXPECTATIVA com imagem bonita → corte seco na batida → REALIDADE com a bagunça → final
- **Ficha:** expectativa (até 40 letras); realidade (até 40 letras); imagens (2)
- **Exemplos:** Confeitaria: bolo de vitrine x cozinha às 3h; Personal: treino de foto x aluno faltando; Restaurante: salão cheio x pia lotada

### 3. Coisas que só quem ___ entende (`so-quem`)

- **Quando usar:** Lista rápida de verdades do ramo que geram identificação e marcações.
- **Formato:** reel, carrossel · 10 a 15 s · voz: não (música) · mídia: nenhuma
- **Cenas:** título 'Coisas que só quem ___ entende' → 4 a 6 cartões trocando na batida → pergunta 'qual é a sua?' → final
- **Ficha:** quem (até 30 letras); itens (4 a 6, até 60 letras cada)
- **Exemplos:** Quem vende doce: o 'faz um descontinho, é pra família'; Quem tem pet shop: banho marcado e o cão rolou na lama; Quem tem bar: o 'último pedido' às 2h

### 4. Os tipos de cliente (`tipos-cliente`)

- **Quando usar:** Retrato divertido dos perfis de cliente que todo negócio tem.
- **Formato:** carrossel, reel · 12 a 18 s · voz: opcional · mídia: nenhuma (ilustração do kit)
- **Cenas:** título 'Os N tipos de cliente de todo ___' → um cartão por tipo: nome + frase típica + ilustração → pergunta 'qual você é?' → final
- **Ficha:** ramo (até 30 letras); tipos (3 a 6: nome até 25 letras, frase até 60)
- **Exemplos:** Hamburgueria: o que tira tudo do lanche; Clínica de estética: a que já leu tudo no TikTok; Loja de roupa: o que prova 12 e leva 1

### 5. Frases que você mais ouve (`frases`)

- **Quando usar:** Frases típicas que o dono escuta, numeradas, pedindo para comentar o número.
- **Formato:** carrossel · 6 a 9 telas · voz: não · mídia: nenhuma
- **Cenas:** capa com a pergunta → uma frase por tela em balão de fala → tela de fechamento com a mensagem do negócio
- **Ficha:** pergunta (até 60 letras); frases (5 a 8, até 70 letras cada); fechamento (até 120 letras)
- **Exemplos:** Salgadeira: 'faz por 50 o cento?'; Fotógrafo: 'é só tirar umas fotinhas'; Marmitaria: 'tem como mandar mais arroz?'

### 6. Conversa no WhatsApp (`chat`)

- **Quando usar:** Conversa encenada entre cliente e dono, com virada no fim (claramente encenada, sem nome real).
- **Formato:** reel · 10 a 15 s · voz: não (som de mensagem + música) · mídia: nenhuma
- **Cenas:** celular com a conversa → mensagens chegando com 'digitando…' → virada (resposta do dono ou do cliente) → final
- **Ficha:** mensagens (4 a 8 falas alternadas, até 80 letras cada); virada (até 60 letras)
- **Exemplos:** Confeitaria: bolo de 3 andares para amanhã; Mecânico: 'quanto fica?' sem dizer o carro; Delivery: 'já saiu?' 2 minutos depois do pedido

### 7. Quiz A, B ou C (`quiz`)

- **Quando usar:** Pergunta com três respostas para comentar; a resposta certa vem no fim e ensina algo.
- **Formato:** carrossel, reel · 4 a 5 telas · voz: não · mídia: 1 foto opcional
- **Cenas:** pergunta com foto → opções A, B e C → 'comenta antes de passar' → resposta com a conta explicada → final
- **Ficha:** pergunta (até 80 letras); opcoes (3, até 20 letras); certa (A, B ou C); explicacao (até 140 letras (números conferidos pelo código))
- **Exemplos:** Confeitaria: preço mínimo do bolo; Academia: quantas calorias tem o açaí; Imobiliária: quanto custa o condomínio de verdade

### 8. Time A ou Time B (`time`)

- **Quando usar:** Tema que divide opinião no ramo para cada um defender o seu lado nos comentários.
- **Formato:** carrossel, reel · 4 telas ou 8 s · voz: não · mídia: 1 foto opcional
- **Cenas:** tela dividida: lado A x lado B → argumento de cada lado → 'comenta o seu time' → fechamento neutro do negócio
- **Ficha:** tema (até 60 letras); lado_a (até 30); lado_b (até 30); argumentos (1 por lado, até 80)
- **Exemplos:** Delivery: taxa à parte ou embutida; Pizzaria: borda recheada sim ou não; Salão: escova ou secar natural

### 9. Mito ou verdade (`mito`)

- **Quando usar:** Crenças comuns do ramo, cada uma com carimbo MITO ou VERDADE e a explicação.
- **Formato:** carrossel, reel · 5 a 7 telas · voz: opcional · mídia: nenhuma
- **Cenas:** capa → afirmação → carimbo MITO/VERDADE batendo → explicação curta → repete por item → final
- **Ficha:** tema (até 50 letras); itens (3 a 5: afirmação até 70, veredito, explicação até 120)
- **Exemplos:** Confeitaria: 'preço alto espanta cliente'; Clínica: 'protetor só no verão'; Mecânico: 'gasolina aditivada limpa o motor'

### 10. Isso ou aquilo (`escolha`)

- **Quando usar:** Pares de produtos do próprio negócio para o cliente escolher; mostra o cardápio sem parecer anúncio.
- **Formato:** reel, story · 8 a 15 s · voz: não (música) · mídia: fotos dos produtos
- **Cenas:** título 'Escolhe um' → 3 a 5 pares de fotos lado a lado com 'ou' → 'conta nos comentários' → final
- **Ficha:** pares (3 a 5 pares de produtos (foto + nome até 25 letras))
- **Exemplos:** Doceria: brigadeiro ou beijinho; Lanchonete: coxinha ou kibe; Loja: tênis branco ou preto

### 11. A conta mudou (`conta-mudou`)

- **Quando usar:** Um custo subiu e o preço não acompanhou: mostra o antes e o depois do lucro.
- **Formato:** reel · 25 a 35 s · voz: sim · mídia: filmagem do banco
- **Cenas:** gancho com o insumo que subiu → preço atual na etiqueta → gráfico do custo subindo → lucro antes x depois → efeito num lote (cento, mês) → frase de virada → final
- **Ficha:** produto (até 25 letras); insumo (até 25); preco (R$); custo_antes (R$); custo_hoje (R$); lote (quantidade (ex.: 100)); falas (6 a 8, geradas e conferidas)
- **Exemplos:** Brigadeiro e o leite condensado; Lava-jato e o produto de limpeza; Marmita e o arroz

### 12. Custo escondido (`custo-escondido`)

- **Quando usar:** Custos que o dono esquece de pôr no preço, somando até o total que some do bolso.
- **Formato:** reel · 25 a 35 s · voz: sim · mídia: filmagem do banco
- **Cenas:** gancho: preço de venda → custo que todo mundo lembra → 'mas tem o que ninguém coloca' → iceberg: custos escondidos aparecendo embaixo d'água → total escondido → final
- **Ficha:** produto (até 25); preco (R$); custo_visivel (R$); escondidos (3 a 6: nome até 25 + R$); falas (geradas)
- **Exemplos:** Cento de salgado: óleo, gás, embalagem, perdas; Corte de cabelo: produto, luz, toalha, comissão; Frete: pedágio, desgaste, tempo parado

### 13. Pra onde vai cada real (`pra-onde-vai`)

- **Quando usar:** Explica o preço mostrando como cada R$ 100 (ou cada venda) se divide.
- **Formato:** reel, carrossel · 20 a 30 s · voz: opcional · mídia: nenhuma
- **Cenas:** nota de R$ 100 na tela → rosca se dividindo em fatias com nome e valor → o que sobra de verdade → final
- **Ficha:** valor (R$ (padrão 100)); fatias (3 a 7: nome até 20 + % (soma 100, conferida pelo código))
- **Exemplos:** Pizzaria: ingredientes, app, entregador, imposto, lucro; Fotógrafo: equipamento, edição, deslocamento; Loja: mercadoria, aluguel, cartão, lucro

### 14. Passo a passo (`passo-a-passo`)

- **Quando usar:** Tutorial curto de algo útil para o cliente (ou para o dono).
- **Formato:** reel, carrossel · 20 a 40 s · voz: sim · mídia: fotos ou filmagem opcional
- **Cenas:** promessa ('como fazer X em N passos') → linha do tempo vertical com cada passo acendendo → resultado → final
- **Ficha:** objetivo (até 60); passos (3 a 6, até 70 letras cada); resultado (até 60)
- **Exemplos:** Confeitaria: congelar bolo sem estragar; Pet shop: escovar o dente do cachorro; Contador: emitir nota como MEI

### 15. Não faça x Faça (`faca-nao-faca`)

- **Quando usar:** Erros comuns e o jeito certo, lado a lado.
- **Formato:** carrossel, reel · 4 a 6 telas · voz: opcional · mídia: fotos opcionais
- **Cenas:** capa 'erros que custam caro' → par vermelho X / verde ✓ por erro → final
- **Ficha:** tema (até 50); pares (3 a 5: erro até 60 + certo até 60)
- **Exemplos:** Delivery: embalagem que vaza; Salão: lavar o cabelo depois da progressiva; Loja virtual: foto com fundo bagunçado

### 16. Número que choca (`numero`)

- **Quando usar:** Um dado forte com fonte, explicado em 3 frases.
- **Formato:** reel, story · 10 a 15 s · voz: opcional · mídia: nenhuma
- **Cenas:** número gigante contando → o que ele significa → fonte pequena → o que fazer com isso → final
- **Ficha:** numero (valor + unidade); significado (até 80); fonte (obrigatória (nome e ano)); acao (até 80)
- **Exemplos:** Pequenos negócios que fecham em 5 anos; Clientes que desistem por demora no WhatsApp; Pedidos feitos depois das 20h

### 17. Checklist (`checklist`)

- **Quando usar:** Lista de conferência que o cliente salva para usar depois.
- **Formato:** carrossel, story · 1 a 3 telas · voz: não · mídia: nenhuma
- **Cenas:** título → itens marcando ✓ um a um → 'salva pra não esquecer' → final
- **Ficha:** titulo (até 50); itens (4 a 8, até 50 letras)
- **Exemplos:** Festa: o que encomendar 15 dias antes; Carro: revisão antes de viajar; Viagem com pet: o que levar

### 18. Comparativo em tabela (`tabela`)

- **Quando usar:** Compara duas ou três opções com dados, linha a linha.
- **Formato:** carrossel, reel · 2 telas ou 15 s · voz: opcional · mídia: nenhuma
- **Cenas:** título → tabela preenchendo linha a linha → destaque da opção vencedora → final
- **Ficha:** opcoes (2 ou 3, até 18 letras); linhas (3 a 6: critério + valor por opção)
- **Exemplos:** Pedido pelo app x pedido direto; Plano mensal x avulso na academia; Aluguel x financiamento

### 19. Demonstração no celular (`demonstracao`)

- **Quando usar:** Mostra o app, site, cardápio digital ou ferramenta funcionando.
- **Formato:** reel · 15 a 25 s · voz: sim · mídia: prints ou gravação da tela
- **Cenas:** problema → celular entrando na tela → toques e telas mudando → resultado → final
- **Ficha:** problema (até 60); telas (2 a 5 prints com legenda até 40); resultado (até 60)
- **Exemplos:** Raiz: calculadora de preço; Restaurante: pedir pelo cardápio digital; Clínica: agendar pelo link

### 20. Oferta relâmpago (`oferta`)

- **Quando usar:** Promoção com preço e prazo.
- **Formato:** reel, story · 8 a 12 s · voz: opcional · mídia: foto do produto
- **Cenas:** produto entrando → preço antigo riscado → preço novo batendo → prazo com contagem → final com a chamada
- **Ficha:** produto (até 30); foto (1); preco_de (R$); preco_por (R$); ate (data/hora); condicao (até 60)
- **Exemplos:** Pizzaria: segunda em dobro; Loja: 20% até domingo; Estética: pacote de 3 sessões

### 21. Lançamento (`lancamento`)

- **Quando usar:** Produto ou serviço novo revelado com suspense.
- **Formato:** reel, story · 10 a 15 s · voz: opcional · mídia: 1 a 3 fotos
- **Cenas:** 'vem novidade' → revelação (cortina ou zoom) → nome + carimbo NOVO → 3 atributos → final
- **Ficha:** nome (até 30); fotos (1 a 3); atributos (3, até 30 letras); quando (opcional)
- **Exemplos:** Doceria: bolo de pote de pistache; Barbearia: corte + barba com toalha quente; Loja: coleção de verão

### 22. Combo ou kit (`combo`)

- **Quando usar:** Itens que se juntam num kit, com a economia em relação a comprar separado.
- **Formato:** reel, carrossel · 10 a 15 s · voz: opcional · mídia: fotos dos itens
- **Cenas:** itens entrando um a um com preço → itens voando para dentro da caixa → preço do combo → 'economia de R$ X' → final
- **Ficha:** nome (até 30); itens (2 a 6: nome + preço avulso + foto); preco_combo (R$)
- **Exemplos:** Hamburgueria: combo família; Kit festa: bolo + 100 docinhos; Salão: dia da noiva

### 23. Cardápio ou catálogo do dia (`cardapio`)

- **Quando usar:** O que tem hoje, com foto e preço, para decidir rápido.
- **Formato:** story, reel, carrossel · 8 a 15 s · voz: não (música) · mídia: fotos dos produtos
- **Cenas:** 'hoje tem' → grade de produtos rolando com nome e preço → carimbo ESGOTADO onde faltar → como pedir → final
- **Ficha:** itens (3 a 9: foto + nome até 25 + preço); esgotados (opcional); como_pedir (até 50)
- **Exemplos:** Marmitaria: pratos do dia; Padaria: fornada da tarde; Brechó: peças novas

### 24. Depoimento de cliente (`depoimento`)

- **Quando usar:** Fala real de um cliente, com permissão; nunca inventada.
- **Formato:** reel, carrossel, story · 8 a 12 s · voz: não · mídia: print ou foto (com permissão)
- **Cenas:** aspas grandes → citação revelada palavra por palavra → nota em estrelas → nome ou primeiro nome + bairro → final
- **Ficha:** citacao (até 160 letras, copiada de mensagem real); autor (primeiro nome); estrelas (1 a 5); prova (id da mensagem ou print guardado)
- **Exemplos:** Confeitaria: avaliação do Google; Oficina: mensagem de agradecimento; Personal: aluno contando o resultado

### 25. Antes e depois (`antes-depois`)

- **Quando usar:** Resultado visual de um serviço: uma barra desliza revelando o depois.
- **Formato:** reel, carrossel · 6 a 10 s · voz: não (música) · mídia: 2 fotos do mesmo ângulo
- **Cenas:** foto ANTES → barra deslizando revela DEPOIS → nome do serviço + tempo → final
- **Ficha:** antes (foto); depois (foto); servico (até 30); detalhe (até 40)
- **Exemplos:** Salão: coloração; Estética automotiva: polimento; Reforma: banheiro

### 26. Como pedir (`como-pedir`)

- **Quando usar:** Explica em 3 passos como comprar, agendar ou encomendar.
- **Formato:** reel, story, carrossel · 10 a 15 s · voz: opcional · mídia: nenhuma
- **Cenas:** 'é fácil pedir' → 3 passos com ícones grandes → canal (link, WhatsApp, endereço) em destaque → final
- **Ficha:** passos (3, até 40 letras); canal (link, número ou endereço); prazo (opcional)
- **Exemplos:** Encomenda de bolo com 3 dias; Agendamento de banho e tosa; Pedido de marmita da semana

### 27. Agenda aberta (`agenda`)

- **Quando usar:** Mostra horários ou datas livres para quem vende por agendamento.
- **Formato:** story, reel · 8 a 12 s · voz: não · mídia: nenhuma
- **Cenas:** calendário da semana → horários livres acendendo, ocupados riscados → 'garanta o seu' → final
- **Ficha:** periodo (semana ou mês); livres (lista de datas/horas); como_agendar (até 50)
- **Exemplos:** Salão: sábado com 2 vagas; Fotógrafo: datas de dezembro; Clínica: avaliações da semana

### 28. Bastidores e história (`bastidores`)

- **Quando usar:** Quem faz, como faz e por que começou, com fotos do próprio negócio.
- **Formato:** reel, carrossel · 15 a 30 s · voz: opcional · mídia: 4 a 8 fotos do cliente
- **Cenas:** foto do dono com o nome → fotos com zoom lento e legendas curtas (3 atos: começo, hoje, amanhã) → final
- **Ficha:** fotos (4 a 8 com legenda até 50); atos (3 frases até 80)
- **Exemplos:** Confeitaria que começou na cozinha de casa; Oficina de pai para filho; Loja que nasceu no Instagram

### 29. Aviso (`aviso`)

- **Quando usar:** Horário especial, feriado, férias, mudança de endereço ou de telefone.
- **Formato:** story, reel · 5 a 8 s · voz: não · mídia: nenhuma
- **Cenas:** ícone do tipo de aviso → data em destaque → o que muda → final
- **Ficha:** tipo (feriado, férias, horário, endereço, telefone); data (data); texto (até 100); volta (opcional)
- **Exemplos:** Fechado no feriado de 15/11; Novo endereço a partir de segunda; Horário estendido no Natal

### 30. Marco e agradecimento (`marco`)

- **Quando usar:** Comemora um número ou data e agradece aos clientes.
- **Formato:** reel, carrossel · 8 a 12 s · voz: opcional · mídia: 1 foto opcional
- **Cenas:** número contando até o marco → confete → obrigado + foto → final
- **Ficha:** numero (valor real); o_que (até 40 (pedidos, anos, clientes)); obrigado (até 100)
- **Exemplos:** 1.000 bolos entregues; 5 anos de oficina; 10 mil seguidores
