---
name: posts-instagram-raiz-carrossel
description: "Criar carrossel ou imagens de post para o Instagram da Raiz Connect (1080x1350) com Pillow, seguindo marca e regras do Matheus, e gravar slides e legenda."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-23
tags: ["aprendizado"]
trigger_patterns:
  - "carrossel"
  - "slides"
  - "post instagram"
  - "legenda"
  - "1080x1350"
  - "marca da Raiz"
  - "logo da Raiz"
  - "calculadora grátis"
---

# Carrossel/post de feed da Raiz (imagens + legenda)

Vale para pedidos de carrossel ou imagem de feed da Raiz Connect gerados por código (Pillow). Publicar ou enviar é outra etapa e só com ordem dele. Em teste "sozinho", decida pelo mais sensato e diga o que decidiu.

## Fluxo
1. **Leia o contexto antes de desenhar.** Se vier `contexto.zip` (a Pasta do Segundo Cérebro), extraia com Python (`zipfile.ZipFile(...).extractall(...)`), pois o `unzip` pode não existir no `terminal`. Leia com `read_file`, nesta ordem: `marca.json` e `marca.md` (cores, fontes, logos), `criterios_ar_board/conteudo.md` e `moldes.md` (regras de post) e as decisões do Matheus sobre posts (`search_files` ou grep por "post", "oferta", "travessão", "emoji", "jargão"). Anote a OFERTA ATUAL da Raiz: ela precisa aparecer no carrossel, em geral no último slide junto da chamada.
2. **Regras de texto que valem sempre:** sem travessão (nem meia-risca), sem emoji, sem jargão (troque "líquida", "canal", "margem", "CMV" por palavras do dia a dia do dono de restaurante), conta com números marcados como EXEMPLO nos slides e na legenda, e chamada para a calculadora grátis do link da bio. Setas: use texto ("Arrasta para o lado") ou desenhe a forma; não use caractere de emoji nem "->" feio.
3. **Marca:** use as cores e fontes do `marca.json`/`marca.md` (fontes ausentes no zip: baixe as oficiais do Google Fonts). Use `logo_claro` em fundo escuro e `logo_escuro` em fundo claro, em TODOS os slides, num canto fixo que não colida com botão ou texto.
4. **Estrutura de 5 slides:** capa com a pergunta do tema; conta de exemplo; resultado em destaque; por que passa batido; chamada final (oferta atual + calculadora grátis na bio). Um conceito por slide, texto grande (mín. ~30 px no corpo), margens de ~56 px.
5. **Escreva um único arquivo `build_carousel.py`** (com `write_file`) com imports, helpers e os 5 slides, e rode no `terminal` com o python do venv. Não espalhe o desenho em células separadas: dá `NameError: Image`. Salve cada slide em `slideN.png` (RGB, 1080x1350).
6. **Confira de verdade:** cheque tamanho de cada PNG, abra os 5 com `vision_analyze` e escreva o que viu (texto cortado, sobreposição com logo, contraste, quebra feia de linha). Corrija e rode de novo antes de entregar. Rode grep (no `terminal`) por `—`, `–` e emojis no script e na legenda. Confira a aritmética do exemplo (soma e porcentagem ditas no texto, ex.: "menos de 35 centavos de cada real" só vale se a conta bate).
7. **Legenda (`legenda.txt`):** curta, em português simples, repete que os valores são exemplo, cita a oferta atual e termina com a chamada da calculadora grátis na bio. Sem hashtags em excesso nem emoji.
8. **Resposta final curta:** o que fez, o que decidiu sozinho (valores de exemplo, paleta, fontes baixadas) e o caminho dos arquivos. Só afirme o que conferiu.

## Armadilhas
- Carrossel sem a oferta atual está incompleto: leia a oferta no contexto antes do slide final, não deixe só a calculadora.
- Palavras técnicas passam batido ao escrever rápido ("sobra líquida", "canal"). Releia todo o texto procurando jargão antes de renderizar.
- Não use cor fora da marca como destaque principal; um acento discreto para despesas é aceitável, mas diga que foi decisão sua.
- O Matheus quer o post corrigido durante a criação (não só no revisor perto de publicar): faça a própria revisão de regras no passo 6.
