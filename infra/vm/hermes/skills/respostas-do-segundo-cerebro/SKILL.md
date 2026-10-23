---
name: respostas-do-segundo-cerebro
description: "Responder perguntas sobre o que o Matheus já registrou (oferta, garantia, cliente ideal, preço em posts, ritmo, posicionamento) usando só o Segundo Cérebro / contexto.zip, citando a fonte de cada resposta."
version: 1.0.1
adaptada_hermes: 2026-10-23
origem_a0: 1.0.1
origem: aprendizado
atualizada: 2026-10-23
tags: ["aprendizado"]
trigger_patterns:
  - "sem pesquisar na web"
  - "só com o que o Matheus já registrou"
  - "cite de onde tirou"
  - "oferta atual"
  - "garantia exata"
  - "quem é o cliente"
  - "contexto.zip"
  - "segundo cérebro"
---

# Responder só com o que o Matheus registrou (Segundo Cérebro)

Vale para pedidos do tipo "sem pesquisar na web, diga qual é a oferta / garantia / cliente / decisão sobre X e cite de onde tirou". A fonte é a Pasta do Segundo Cérebro (`contexto.zip`, ou as ferramentas `decisao`/`cerebro` quando não houver zip). Consultas de cotação e Gmail: skill consultas-rapidas.

## Fluxo
1. **Extraia com Python** (`execute_code`), não com `unzip` (pode não existir): `zipfile.ZipFile(zip).extractall(destino)`. Liste as pastas: `segundo_cerebro/Decisoes/`, `segundo_cerebro/Raiz/` (oferta, marca, cliente-ideal, playbook, mapa), `segundo_cerebro/Assuntos/`, `criterios_ar_board/`.
2. **Comece pelo mapa**: `Raiz/mapa.md` e `Decisoes/indice.md` dizem qual arquivo é a fonte de cada tema (ex.: oferta, preço, garantia, links ficam em `Raiz/oferta.md`).
3. **Busque pelo CONTEÚDO, não pelo nome do arquivo**: no `terminal`, `grep -rliE 'termo1|termo2' segundo_cerebro/ criterios_ar_board/` (ou `search_files`; inclua variações com e sem acento: `preço|preco`). Os nomes dos arquivos de decisão são truncados e enganam. Depois leia por inteiro (`read_file` ou `cat`) os arquivos achados.
4. **Confira o campo `estado:` de cada decisão.** `substituida` (há `substituida_por`) não vale mais: siga para a decisão nova e cite essa. Quando duas decisões ativas se completam (ex.: cliente original + público ampliado depois), diga as duas, com a ordem no tempo.
5. **Procure a resposta nos arquivos `Raiz/` antes de dizer que não há decisão.** Regras sobre "mostrar X em post/story" costumam estar em seções de `Raiz/oferta.md` (ex.: "No post público x na conversa privada"), não numa decisão com esse título. Se de fato só existir decisão indireta (ex.: stories entram na mesma aprovação dos posts), diga isso e registre como o que você decidiu sozinho.
6. **Grave a resposta em arquivo** (`write_file`) na pasta pedida, uma seção por pergunta: resposta literal (garantia com as palavras exatas, nome da oferta, números), e abaixo "Citado de: `caminho/relativo.md`" para cada uma. Confira no `terminal` com `wc -l` e `head`.
7. **Resposta final curta**: uma a duas linhas por pergunta com a fonte entre parênteses, o que decidiu sozinho, caminho do arquivo.

## Armadilhas
- **Não parafraseie a garantia nem o nome da oferta**: copie do arquivo. Detalhes que mudam o sentido ("não é devolução de dinheiro, é não cobrar a próxima mensalidade") entram na resposta.
- **Separe o canal**: regras de oferta mudam entre post público e conversa privada da prospecção (link, receita, vaga). Diga a qual das duas a resposta se refere.
- **Nomes antigos descartados** (ex.: o nome anterior da oferta) só aparecem como "saiu de tudo", nunca como a oferta atual.
- **Sem web**: se o pedido proíbe pesquisar, não abra navegador (`browser_navigate`) nem use `web_search`/`web_extract`; link externo do plano de marketing que não abre é dito como limite, não inventado.
- **Não tire da cabeça o que o arquivo não diz**: valores, prazos e vagas só como estão no texto. Cite a fala do Matheus (campo `citacao`) só quando for a forma mais clara.
