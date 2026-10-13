# Como construir um molde

Um molde é uma animação fixa (ou um carrossel) que recebe uma **ficha** curta e uma **marca** e vira post. O agente só
preenche a ficha; nunca mexe no código. Especificação de cada molde: `../catalogo.json` (situação, formatos, cenas,
ficha, regras). Plano: `docs/MOLDES_VIDEO.md`. Referências prontas: `../conta-mudou/` (Reel narrado) e
`../cardapio/` (story, Reel e carrossel com fotos).

## Arquivos de um molde `<id>/`

| Arquivo | O quê |
|---|---|
| `molde.html` | cenas + `Motor.molde({...})` |
| `esquema.json` | `formatos`, `voz` (`sim`, `nao`, `opcional`), `musica` (nome do banco ou null) e `campos` da ficha |
| `exemplos/*.json` | 3 ou mais fichas de teste, de pelo menos 2 marcas (estilos diferentes), cobrindo todos os formatos |
| `exemplos/recusadas/*.json` | pelo menos 1 ficha que tem de ser recusada (ex.: dado real sem `_origem`, travessão, item demais) |
| `exemplos/recusadas-molde/*.json` | fichas que passam no validador mas o **molde** recusa com `$m.erro` (prazo vencido, combo mais caro); o `testar.py` exige saída 2 |

Rodar: `python3 testar.py <id>` (prévia + conferência de todas as fichas; tem de dar ✓). Uma ficha só:
`python3 motor/render.py <id> <id>/exemplos/x.json --previa [--area]` → `<id>/saida/x-<formato>/prev.jpg` (folha de
quadros; `--area` desenha a área livre do Instagram). Sem `--previa` gera o vídeo ou os slides finais.

## Ficha e esquema

- Campos especiais da ficha: `_marca` (pasta em `marcas/`), `_formato`, `_estilo` (troca o estilo da marca),
  `_origem` (`{"campo": "dono" | "sistema"}` para todo campo `real`), `_voz` (false desliga narração opcional),
  `_musica`. Livres em qualquer molde: `chamada` (até 32 letras), `final_extra` (até 70), `nota` (ex.: "valores de
  exemplo").
- Tipos de campo: `texto` (`max`, `min`), `numero`, `dinheiro`, `porcentagem` (`min`, `max`), `data` (AAAA-MM-DD),
  `hora` (HH:MM), `foto`, `filmagem`, `escolha` (`opcoes`), `booleano`, `lista` (`min`, `max`, `item`: um tipo ou um
  objeto de campos), `objeto` (`campos`). `obrigatorio: false` para opcional. `real: true` = dado do negócio (preço,
  custo, horário, depoimento, número de marco, fonte): sem ele e sem `_origem` a ficha é recusada e o agente troca
  de molde.
- O validador já recusa travessão (— e –) e emoji em qualquer texto. Os limites de letras devem ser os que cabem
  no layout com folga: é o limite que impede texto cortado, não a sorte.

## molde.html

```html
<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="../motor/motor.css">
<style>/* só posições e tamanhos; cores SEMPRE por var(--…) */</style></head><body><div id="palco">
<div class="cena" id="c0"><div class="cam full"> … </div></div>
</div>
<script src="../motor/motor.js"></script>
<script>
Motor.molde({
  id: '<id>', formatos: ['reel', 'story', 'carrossel'],
  montar(F, M, $m) { /* vídeo: preenche o DOM com F (textContent!) e devolve {duracoes:[…]} se não tiver voz */ },
  quadro(t, F, $m) { /* vídeo: anima o instante t (em segundos) */ },
  slides(F, M, $m) { /* carrossel: cria os .slide no #palco (e remove as .cena) */ },
});
</script></body></html>
```

O motor faz sozinho: cores da marca no estilo (`vidro`, `claro`, `pop`, `papel`, `noite`), fundo animado, grão,
marca d'água, a **cena final** (logo grande, chamada, @), o **slide final** do carrossel, a transição entre cenas
conforme o estilo, o ajuste de tamanho do texto e a conferência.

### Linha do tempo

- **Com voz** (`voz: sim`): `F.falas` é a narração; a cena *i* dura a fala *i*; a última fala é a chamada e vira a
  cena final do motor. `montar` não devolve durações.
- **Sem voz**: `montar` devolve `{duracoes: [s, s, …]}` (uma por cena, sem a final); o motor soma 3 s de cena final
  e põe a música do banco (`esquema.musica`). Duração total dentro do catálogo.
- `$m.ini(i)`, `$m.fim(i)`: início e fim da cena *i*. `$m.cena('#id', t, i[, j, {trans, x, y, push}])` mostra a cena
  durante *i…j* com a transição do estilo e devolve o progresso de entrada.

### Ferramentas do `$m` (Motor)

| | |
|---|---|
| `$`, `$$` | querySelector / All |
| `p(t, a, d)` | progresso 0..1 de *a* a *a+d*; com `eo`, `eo5`, `eio`, `eb` (estouro), `el` (elástico), `lerp`, `cl` |
| `revela(el, t, t0[, passo, dur])` | texto aparecendo palavra por palavra (o elemento precisa da classe `rv`) |
| `entra(el, t, t0[, dur, dy, escala])` | entrada suave; devolve o progresso |
| `conta(el, t, t0, dur, valor[, fmt, de])` | número contando |
| `carimbo(el, t, t0)` | carimbo batendo (MITO, ESGOTADO, NOVO) |
| `marcador(el, t, t0)` | marca-texto atrás de um `<span class="mk">` |
| `brilho(btn, t, t0)` | brilho passando (botão com `<i>` dentro) |
| `filmagem(img, valor, t)` | fundo em movimento: nome do banco ou de um vídeo do cliente (`midia/filmagem/<nome>`, feito por `motor/video_cliente.py`) **ou** caminho de foto do cliente (`fotos/x.jpg`), que ganha zoom lento. Use sempre esta função para fundo: assim todo molde aceita a mídia do próprio negócio |
| `midia(caminho)` | caminho de foto da ficha (`fotos/x.jpg` → `midia/fotos/x.jpg`) |
| `icone(nome)` | ícone SVG (lista em `motor.js`, objeto `P`: check, x, estrela, relogio, calendario, local, telefone, chat, carrinho, moto, cartao, dinheiro, presente, coracao, fogo, etiqueta, caixa, camera, tesoura, chave, bolo, xicara, pata, casa, pessoa, pessoas, megafone, brilho, seta, info, alerta, cadeado, folha, link, grafico, percentual, trofeu, balao, lupa, mais, menos, carro, haltere, dente, vestido, garfo) |
| `brl(v[, casas])`, `num(v[, casas])` | dinheiro e número em pt-BR |
| `erro(msg)` | dado que não fecha (combo mais caro que avulso, prazo vencido): o molde recusa |
| `FORMATO`, `ESTILO`, `H` | formato atual, estilo, altura (1920 ou 1350) |

### Classes e tokens

- Texto: `t` em **todo** texto visível (é medido: precisa caber na caixa; dê **largura e altura** fixas para ele
  poder encolher), `seg` no que é importante (tem de ficar na área livre), `rv` no que usa `revela`, `tit` (fonte de
  título da marca), `t2` (texto secundário), `dest` (cor de destaque), `chip` (pílula de destaque), `grad`, `mk`
  (marca-texto), `mao` (letra de mão), `cartao` (cartão cujo visual muda por estilo), `ctr` (centralizado).
- Cores: `var(--fundo)`, `--fundo2`, `--texto`, `--texto2`, `--destaque`, `--sobre-destaque` (texto em cima do
  destaque), `--c1`, `--c2`, `--cartao`, `--borda`, `--sombra`, `--bom`/`--sobre-bom`, `--ruim`/`--sobre-ruim`.
  Fontes: `var(--ft)` (título da marca), `var(--fb)` (texto), `H` (mão). **Nunca** escreva uma cor literal nem
  `#fff`: o mesmo molde tem de funcionar em fundo escuro, claro e colorido. Exceção: texto branco sobre foto escurecida
  por degradê preto.
- Letra mínima: 30 px no Reel e no story, 26 px no carrossel (o ajuste para aí e a conferência reprova abaixo).
- Valor que muda na animação (número contando): ponha o valor final no `montar`, para o ajuste medir o maior.
- Texto `rv` não pode ser filho direto de uma caixa `display:flex` (cada palavra vira um item e o texto se desmonta): ponha o texto numa `div` dentro dela.
- Campo `real` opcional: `"real": true, "obrigatorio": false` (sem valor passa; com valor exige `_origem`).

### Onde pode ir texto (área livre do Instagram)

| Formato | Tela | Conteúdo | Marca d'água |
|---|---|---|---|
| Reel | 1080x1920 | y de 370 a 1480; da metade para baixo (y > 900) só até x = 910 (botões à direita) | topo, y 258 a 330 |
| Story | 1080x1920 | y de 370 a 1560, x de 60 a 1020 | topo, y 258 a 330 |
| Carrossel | 1080x1350 | x de 84 a 996, y de 130 a 1280 | canto, x 84, y 64 |

O zoom de câmera (`.cam`) cresce uns 5%: deixe margem. Imagem e fundo podem ir até a borda; só o texto e o
logo são conferidos.

## Qualidade: o que é um molde pronto

1. `python3 testar.py <id>` dá ✓.
2. Você **olhou** a `prev.jpg` de cada ficha (ferramenta Read) e não há: texto sobreposto, texto miúdo perdido em
   tela vazia, cartão vazio, contraste ruim, elemento cortado na borda, cena igual à anterior, "cara de template".
   Cada cena tem uma composição clara, uma coisa principal, movimento com propósito.
3. Ele é **diferente** dos outros moldes: a animação principal descrita no catálogo (iceberg, rosca, chat, carimbo,
   barra de antes e depois, calendário…) existe e é o momento do vídeo.
4. Funciona nos 5 estilos (as fichas de teste usam pelo menos 2; troque `_estilo` para conferir os outros).
5. Regras do catálogo (`regras` do molde e `padrao_de_todo_molde`) estão no código ou no esquema: dado real exige
   `_origem`; o que é conta é feito pelo código; nada inventado.

Mídia de teste disponível: `midia/fotos/*.jpg` (comida: acai, bolo, brigadeiro, confeita, delivery, embala, forno,
freezer, fritura, gas, geral, lanche, leite, maquina, pizza, relogio, salgado; oficina: oficina_antes,
oficina_depois, oficina_interior, mecanico_maos; salão: salao_antes) e `midia/filmagem/<nome>` com os mesmos nomes
de comida. Marcas de teste: `cantina-da-vo` (vidro, assina com foto em vez de logo), `raiz` (vidro), `doces-da-lu` (claro), `oficina-do-ze` (pop), `studio-bella` (papel, só
logo claro), `burger-noite` (noite, logo vai em selo), `sem-logo` (claro, só o nome).
