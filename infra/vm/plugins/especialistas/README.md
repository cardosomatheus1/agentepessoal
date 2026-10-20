# especialistas

Especialista (GLOSSARY.md): um papel com personalidade e regras próprias que o agente principal chama para uma tarefa e
que usa o mesmo Segundo Cérebro. O Matheus não fala com ele direto.

- **Crítico** (`criticar(tipo, material) -> {veredito, motivos, sugestoes, avisos}`, `tipo` post | carrossel | oferta |
  landing | mensagem): uma chamada ao modelo (`openai.gpt-6-luna` no endpoint local, cabeçalho `X-A0-Dono`), com o
  Cérebro da Raiz (`cerebro/helpers/raiz.py` `contexto()`) e os critérios do AR Board (`calibracao/<agente>/criterios.md`:
  post/carrossel → conteudo + moldes, oferta/landing → conteudo, mensagem → prospeccao). Aceita imagens
  (`material["imagens"]`, enviadas como `input_image`). Sem o Cérebro ou sem critérios ele julga mesmo assim e diz em
  `avisos`. **Fail closed:** só vale JSON com `veredito` aprova|reprova e listas de texto; qualquer outra coisa, ou o
  modelo fora do ar, é "reprova". Regras fixas checadas por código reprovam mesmo com o modelo aprovando: emoji,
  travessão, R$ sem "valores de exemplo" (post e carrossel).
- **Designer** (`desenhar(briefing) -> {spec, arquivos, critica, falta, render}`): transforma o briefing numa ficha
  para o motor de `infra/reels`:
  - `carrossel_raiz`: conceito + slides no kit da Raiz (base `raiz-carrossel.css/js`). Cada carrossel da Raiz é um
    `index.html` próprio (liberdade criativa do kit), então o plugin entrega a ficha e o comando
    (`base/carrossel.py c_<nome>` + `base/validar_carrossel.py`), não os slides.
  - `video_kit_raiz`: roteiro por cena; o kit de motion mora no repositório erp-saas, fora do alcance do agente.
  - `molde`: só outras marcas (a Raiz não usa moldes desde 14/10). A ficha passa pelo `moldes/motor/validar.py` e, se o
    motor e o Playwright estão na máquina, é renderizada por `moldes/motor/render.py` (arquivos em
    `/a0/usr/workdir/especialistas/<hora>/`).
  Toda saída passa pelo Crítico (`critica`), com as imagens renderizadas.
- Ferramenta `especialista` (`acao` criticar | desenhar): o agente chama antes de publicar ou mandar qualquer coisa
  pública. Aprovado não é ordem de publicar.
- Onde procura o motor e a calibração: `ESPECIALISTAS_REELS` / `ESPECIALISTAS_CALIBRACAO`, depois o repositório ao lado
  do plugin, depois `/a0/usr/reels` e `/a0/usr/calibracao`.
- Testes: `python3 tests/suite.py` (modelo, render e Cérebro simulados; sem rede).
