# Criador de vídeos do NEXOS — pacote para o orquestrador (Main Opus NEXOS)

Decidido com o Matheus em 21/10/2026 (grilling, 16 perguntas, todas fechadas; fala dele: "Tudo ok", "Cria como
storys no nexos, inclusive no linear ... detalhar td, fornecer link, motor e etc, td q ele precisa pra fazer
corretamente"). Este arquivo é **insumo**: as Story Cards, os ids, o encaixe nos bounded contexts, eventos, ADRs e o
espelho no Linear são feitos pelo orquestrador do NEXOS pelas regras do repositório dele (STORY_CARD_STANDARD,
`build_state.py`, `/sync-linear`). Nada aqui autoriza pular gate, piloto ou ação governada.

**Atualizado em 22/10/2026** (Matheus: "Atualize"): motor no commit `474feda` (render no runtime sem Playwright, tela
do sistema inteira, estilo kit, fontes novas), o Crítico como ele julga hoje e o ciclo Designer ↔ Crítico que o agente
usa na criação (seções 4, 4.1 e 6). Até 22/10 nenhuma Story do Criador existia no NEXOS nem no Linear.

## 1. O que é (uma frase)

Uma página do NEXOS onde o dono do restaurante faz sozinho um vídeo vertical de divulgação: põe a logo e 2 cores,
escreve uma frase do que quer, escolhe 1 de 3 Moldes sugeridos, recebe o vídeo conferido e baixa.

## 2. Decisões do Matheus (fonte: `docs/MOLDES_VIDEO.md` §6 "Criador de vídeos do NEXOS")

| # | Decisão |
|---|---|
| Q1 | Quem usa: o dono do restaurante, sozinho, no painel do NEXOS (se a equipe operar no começo, é a mesma tela). |
| Q2 | Vídeo vertical 1080x1920, 15 a 60 s, Instagram/WhatsApp. Fora da 1ª versão: anúncio pago, vídeo longo. |
| Q3 | Campos: logo, 2 cores base, uma frase do que quer, fotos dos pratos (opcional). Nome, endereço, WhatsApp, cardápio vêm do NEXOS. Logo e cores ficam salvos (Marca) depois da 1ª vez. |
| Q4 | A IA sugere 3 Moldes com Prévia; o cliente escolhe; nunca vê o catálogo inteiro. |
| Q5 | Conteúdo que não cabe (texto longo, foto ruim, cor sem contraste): ajuste automático. Pedido que nenhum Molde atende: a página diz o que não dá e oferece os 3 mais próximos. |
| Q6 | Vê o vídeo pronto; até 2 ajustes grátis (cada ajuste = vídeo novo); só baixar na 1ª versão (publicar direto depois). |
| Q7 | Limite mensal de vídeos por plano (ex.: 10 básico, 30 profissional; número final depende dos planos do NEXOS); sem avulso na 1ª versão; ajuste não conta. |
| Q8 | Nenhum Molde novo criado na hora; todo Pedido sem molde é guardado e vira a fila do que construir. |
| Q9 | Foto do prato só a do cliente (ajuste automático de recorte, luz, tamanho; se continuar ruim, pede outra). A IA **nunca** inventa foto do prato; no máximo fundo/ambiente. |
| Q10 | Voz Carolina por padrão ou "sem voz"; música só do banco CC0 do motor; cliente não sobe música. |
| Q11 | Motor e catálogo copiados para dentro do NEXOS como peça própria; nunca depender do agente pessoal do Matheus. |
| Q12 | Entra depois do MVP atual, como frente de crescimento do cliente; não aumenta o primeiro piloto sem decisão dele. |
| Q13 | Entram todos os Moldes do catálogo, menos os rejeitados pelo Matheus no AR Board ("pode aprovar os outros, estão bons no geral"). Hoje rejeitados: `pov` e `pergunta-cliente` (rodada 2). |
| Q14 | Prévia = imagem parada do Molde com a Marca do cliente (grátis, segundos); vídeo completo só depois da escolha. |
| Q15 | Antes de mostrar: conferências do motor + Crítico; reprovou, refaz 1 vez; reprovou de novo, oferece outro Molde. Cliente nunca vê vídeo reprovado. |
| Q16 | Biblioteca do restaurante guarda os vídeos 90 dias; depois apaga o vídeo e guarda a Ficha (regerar). |

## 3. Glossário (usar estes nomes na UI e no código; fonte: `GLOSSARY.md` §Vídeos)

- **Molde**: vídeo-modelo pronto (animação, cenas, limites de texto) que vira o vídeo de qualquer empresa ao receber Marca e Ficha. Evitar: template, tema.
- **Marca**: logo, 2 a 4 cores, fonte, @, chamada, voz; preenchida uma vez. Evitar: identidade visual, branding.
- **Ficha**: o conteúdo de um vídeo (falas, números, fotos) que preenche os campos de um Molde. Evitar: roteiro, briefing.
- **Prévia**: imagem parada do Molde já com a Marca do cliente. Evitar: thumbnail, rascunho.
- **Pedido sem molde**: pedido que nenhum Molde atende; guardado para decidir o que construir. Evitar: molde sob medida.

## 4. O motor (o que já existe e está provado)

Código (Python + JS, sem dependência paga): repositório `cardosomatheus1/agentepessoal`, branch `ccr-bcbe3101-9u4klv`,
commit `474feda0d819caf9a9abec5e71c531cbf7a43b04`, pasta `infra/reels/moldes/`.
https://github.com/cardosomatheus1/agentepessoal/tree/474feda0d819caf9a9abec5e71c531cbf7a43b04/infra/reels/moldes

Pacotes prontos (mesma conta AWS do NEXOS):
- `s3://agentepessoal-backup-964862484412/nexos/criador-videos/moldes-codigo-474feda.tgz` (35 MB; `infra/reels/moldes`
  versionado + `docs/MOLDES_VIDEO.md` + `calibracao/moldes` + `GLOSSARY.md` + o Crítico e o Designer do agente
  (`infra/vm/plugins/especialistas/helpers/especialistas.py`) e o ciclo de conferência
  (`infra/vm/plugins/conteudo/helpers/conteudo.py`, `semana.py`); sha256 começa com `c78cfc67e1db552f`). O pacote
  antigo `moldes-codigo-c3e618c.tgz` fica só de histórico: não use.
- `s3://agentepessoal-backup-964862484412/nexos/criador-videos/moldes-midia.tgz` (487 MB; `midia/filmagem` e
  `midia/fotos`: banco de filmagens/fotos de reserva geradas por nós; sha256 começa com `4cadd7e6b55af569`).
- Este arquivo: `s3://agentepessoal-backup-964862484412/nexos/criador-videos/CRIADOR_VIDEOS_HANDOFF.md`.

Leitura obrigatória antes de qualquer card: `docs/MOLDES_VIDEO.md` (plano, regras, custo, catálogo, detalhe de cada
Molde) e `infra/reels/moldes/motor/LEIAME.md` (como um Molde é construído).

Como funciona:
- **Três camadas**: Molde (`<molde>/molde.html` com `Motor.molde({montar, quadro, slides})`, `esquema.json` com
  formatos, voz, música e campos da Ficha com limite de letras, `exemplos/`), Marca (`marcas/<id>/marca.json`) e Ficha.
- **Catálogo**: `catalogo.json` v2: 5 estilos (vidro, claro, pop, papel, noite), 13 blocos, 65 Moldes (Vender 21,
  Ensinar 13, Engajar 10, Lançar 9, Atrair 7, Institucional 5). Cada Molde declara para quem fala (cliente final ou
  dono): para restaurante vendendo ao público só os que falam com o cliente final (critério 4 abaixo).
- **Marca aplicada pelo motor** (`motor/motor.js`): cores por variáveis CSS (`--fundo`, `--destaque`…), cor fixa é
  proibida, contraste ajustado sozinho, logo como marca d'água no topo e grande na cena final com @ e chamada; sem
  logo usa foto ou nome; sem cores, paleta tirada da logo.
- **Render** (`motor/render.py`): Chromium headless (Playwright) captura quadros com `render(t)` em processos paralelos
  e ffmpeg monta 1080x1920, 30 fps, áudio a -14 LUFS. Remotion foi descartado (licença paga para empresa). Mídia do
  cliente: foto ganha zoom lento; vídeo do cliente vira quadros (`motor/video_cliente.py`).
- **Conferência automática**: `motor/validar.py` (texto acima do limite, travessão, emoji, campo `real` sem `_origem`);
  `Motor.conferir()` (texto que não cabe, letra pequena, fora da área livre do Instagram, sobre a marca d'água,
  contraste baixo); `render.py` confere tempo de leitura e transcreve a voz palavra por palavra e refaz se diferir
  (saída 3 = problema, relatório em `relatorio.json`). Crítico (julga quadros renderizados com os critérios do AR
  Board) mora hoje no agente: `infra/vm/plugins/especialistas/helpers/especialistas.py`; no NEXOS vira um
  SemanticDecision com os critérios da seção 6 como calibração.
- **Testes existentes**: `motor/test_validar.py`, `test_voz.py`, `test_audio.py`, `test_gerar_foto.py`.
- **Mudanças de 21 a 22/10 que importam para o NEXOS** (`git diff c3e618c 474feda -- infra/reels/moldes`):
  - `render.py` roda também com **patchright** (o runtime do servidor não tem Playwright) e avalia o Molde no mundo
    da página; antes todo render no servidor parava em 60 s. Teste: `motor/test_patchright.py`.
  - Tela de sistema/app é mostrada **sempre inteira**, nunca recortada para encher a caixa (decisão do Matheus #85;
    `_telasInteiras` em `motor.js`). Para o NEXOS vale para foto de cardápio ou print que o cliente subir.
  - Estilo **kit** (fontes Manrope e Instrument Serif, OFL, em `motor/fontes`), logo sem textos de produto.
  - Prévia por cena usa o quadro do **fim** da cena (onde o texto já entrou), não o do começo.
  - `motor/credencial_voz.py`: a voz usa credencial curta própria; o render não depende da credencial do agente.
- **Voz**: Amazon Nova 2 Sonic, voz Carolina (`motor/voz_sonic.mjs`). O texto antigo cita Polly; vale Sonic.
- **Licenças**: músicas só CC0 (`motor/musica/licencas.json`), fontes só OFL (`motor/fontes`), filmagens geradas por nós.

### 4.1 Crítico e ciclo de criação, como funcionam no agente desde 22/10

**Crítico** (`criticar(tipo, material)` em `especialistas.py`): modelo separado, que vê as imagens renderizadas (até 10
por chamada, um carrossel inteiro) e o texto, e responde só JSON `{veredito: aprova|reprova, motivos, sugestoes}`;
resposta ilegível = reprova (falha fechada). Regras de julgamento ajustadas pelo Matheus em 22/10 ("o crítico q ta
pegando demais"):
- **Reprova só por:** regra do Matheus quebrada (decisão, AR Board, Cérebro da marca), informação falsa ou sem origem,
  texto cortado ou ilegível que ele viu na imagem, promessa que o produto não cumpre, ideia mole ou genérica.
- **Vai em sugestões, não reprova:** melhoria, gosto, "pode ser entendido como…"; peça curta que não traz a oferta
  inteira (story/quiz mostram uma parte; o resto está no link).
- Antes de reprovar por algo da imagem, olha de novo e cita o slide e o texto exato; o que não confirmou não é motivo.
- Fala e troca de cena podem desencontrar até 1 s sem reprovar.
- **Crítico fora do ar não é reprovação:** tenta de novo; nunca libera sem veredito.
- Lê o Cérebro da marca inteiro (a oferta era cortada em ~1000 letras) e os critérios do AR Board.

**Designer ↔ Crítico** (`revisar(...)`, `REVISOES = 2`): o Designer escolhe o Molde do formato pedido, escreve a Ficha,
renderiza, vê as próprias imagens, manda ao Crítico e corrige pelos motivos até 2 vezes antes de entregar. A recusa do
Molde na hora do render (ex.: vídeo curto demais para as falas) entra na correção como mais um motivo.

**Reprovado é refeito na criação, não na hora de publicar** (Matheus, 22/10: "Se o crítico rejeita, automaticamente
deveria ser refeito, e não logo antes de postar, durante a etapa de criação"): `conferir_antes` julga cada peça assim
que é criada (até 36 h antes), refaz sozinho até 2 vezes (`REFAZER_MAX`, `REFAZER_STORY`) e, se ainda reprovar, avisa
com antecedência. A aprovação vale para aqueles arquivos e aquele texto (hash `impressao`): mudou um arquivo, julga de
novo.

**Como isso encaixa no NEXOS (V4):** o mesmo desenho, com o cliente no lugar do Matheus: o cliente nunca vê vídeo
reprovado; a Q15 dele continua valendo (reprovou → refaz 1 vez → reprovou de novo → oferece outro Molde), e as
correções internas Designer ↔ Crítico acontecem antes dessa refação, sem o cliente esperar a mais do que o limite de
tempo da página. O Crítico vira um SemanticDecision (proposta/evidência, nunca autoridade), com as regras acima e a
seção 6 como calibração; "Crítico fora do ar" = estado de espera visível, nunca vídeo liberado sem veredito.

Custo por vídeo (medido no agente): Ficha por modelo barato (centavos) + voz ~US$ 0,02/min + foto de fundo só se
faltar (gpt-image-2 ~US$ 0,06 ou Stability ~US$ 0,04) + render grátis (servidor próprio) = **abaixo de US$ 0,15**.
Prévia (imagem parada) não chama voz nem foto: custo zero.

## 5. Stories propostas (o orquestrador decide fase, ids, owner, prerequisites e quebra final)

Sugestão de encaixe: frente de crescimento do cliente, depois do MVP (Q12); revisar contra `ROS-F9-015
customer-growth-results` e `ROS-F10-008 library-ux`. Não há card de vídeo hoje (`ROS-F9-005 media-agent` é
pacing de mídia paga, não criação).

**V1 — Motor de vídeo como peça própria do NEXOS.** Trazer `infra/reels/moldes` para o NEXOS atrás de uma porta
(ex.: `VideoRenderPort`: `prever(molde, marca, ficha) -> imagem`, `renderizar(...) -> vídeo + relatório`), worker
assíncrono com fila, armazenamento de mídia, sem chamar o agente pessoal. Aceite: os exemplos de 3 Moldes de ramos
diferentes renderizam idênticos ao agente (mesma duração, conferência passando); testes do motor portados; licenças
(CC0/OFL) inventariadas; render sem rede externa exceto voz.

**V2 — Marca do restaurante.** Logo (claro/escuro), 2 a 4 cores, fonte, @, chamada, voz, salvos uma vez; nome,
endereço, WhatsApp e cardápio lidos do NEXOS (sem segunda fonte de verdade). Aceite: segunda visita não pede logo nem
cores; logo enviado passa por validação de upload (tipo, tamanho, conteúdo).

**V3 — Sugestão de Moldes e Prévia.** Frase do cliente → 3 Moldes (SemanticDecisionPort: proposta, nunca autoridade;
filtros determinísticos antes: formato, mídia disponível, Molde fala com cliente final, Molde não rejeitado);
Prévia em imagem com a Marca. Pedido sem molde quando nenhum passa. Aceite: casos de calibração separados (held-out)
com frases reais de restaurante; nunca sugere Molde rejeitado; Prévia sem custo de voz/foto.

**V4 — Ficha, adaptação e conferência.** Ficha escrita a partir da frase + dados do NEXOS, cortada ao limite de cada
campo; foto do cliente ajustada (recorte, luz, tamanho) ou pedido de outra; foto do prato nunca gerada; conferências
do motor + Crítico; refaz 1 vez; reprovou de novo, oferece outro Molde. Aceite: nenhum vídeo reprovado chega ao
cliente (teste com fichas ruins de propósito); números e preços vêm do cardápio do NEXOS (conta é do código).

**V5 — Página do Criador.** Fluxo: Marca (1ª vez) → frase + fotos → 3 Prévias → vídeo → até 2 ajustes → baixar.
Linguagem de negócio, sem termo técnico; voz Carolina ou "sem voz"; música do banco. Segue
`PREMIUM_EXPERIENCE_PRINCIPLES.md` + `UX_QUALITY_GATE.md`. Aceite: dono faz o 1º vídeo sem ajuda em poucos minutos;
estados de espera/erro claros; celular e computador.

**V6 — Biblioteca, limite e custo.** Biblioteca do restaurante (vídeos 90 dias; depois apaga o vídeo e guarda a
Ficha); limite mensal por plano (ajuste não conta; número final por decisão do Matheus); custo de cada vídeo medido
e registrado (decimal, moeda explícita). Aceite: limite bloqueia o 11º vídeo do básico com mensagem clara; expurgo
aos 90 dias verificado.

**V7 — Pedidos sem molde e curadoria do catálogo.** Lista dos Pedidos sem molde para o time decidir o que construir;
marcação no catálogo de Molde aprovado/rejeitado pelo AR Board (rejeitado nunca aparece). Aceite: pedido sem molde
registrado com a frase e o ramo; trocar um Molde para rejeitado o tira das sugestões na hora.

**V8 — Gate de aceite do Criador.** Golden journey ponta a ponta com uma marca de teste, custo por vídeo medido,
nenhum efeito externo (só baixar). Publicar no Instagram é outra Story futura e passa pela ação governada.

## 6. Critérios de qualidade do Matheus (calibração; fonte `calibracao/moldes/criterios.md` + `casos.jsonl`)

1. A imagem tem de ser do que o texto fala. 2. Foto real do produto em todo Molde. 3. Post é anúncio: divulga o
negócio; curto demais e sem mensagem reprova. 4. Fala com o cliente do negócio, não com o dono (para restaurante).
5. Tempo para ler. 6. Quiz com pista antes da pergunta. 7. Data e tema que façam sentido para o ramo. 8. História
com começo, meio e fim. 9. Logo é do negócio do post. 10. História com conclusão. 11. Ligação entre o assunto e o
produto. 12. Não alongar o que é só informação. 13. Molde que fala com o dono só com dor que o anunciante resolve.
Da rodada de lançamento (14/10): voz Carolina em todos; no manifesto, tirar a contagem "1 2 3 4".
Rodadas e vereditos no AR Board: https://claude.ai/artifact/7LFmwYACCRBHspUv9QGwcx (rodada `moldes-2026-10-21-onda3`,
30 Moldes novos, ainda sem julgamento em 22/10; vale Q13: entram, mas sem crivo dele, então na sugestão ficam atrás
dos já aprovados até ele julgar).
Regras que o Matheus deu em 22/10 para os posts da Raiz e que valem para qualquer Molde: tela do sistema/app inteira
(#85); a fala final e a legenda levam à oferta com um passo concreto; termo técnico (ex.: CMV) é explicado na primeira
vez que aparece; logo sem texto de produto.

## 7. Fronteiras (não fazer)

- Não publicar em rede social nem mandar mensagem: só gerar e baixar (publicar = Story futura via ação governada).
- Não gerar foto de prato; não aceitar música do cliente.
- Não criar Molde novo a pedido do cliente em tempo real.
- Não chamar o agente pessoal do Matheus nem a VM dele em produção.
- Nada a cliente real antes do gate de piloto do NEXOS (`ROS-F9-013`).
- Dados de upload do cliente são dele: apagar junto com a conta (erasure).

## 8. Contato e dúvidas

Dúvida de produto: perguntar ao Matheus. Dúvida do motor: sessão do operador do agente pessoal (que escreveu este
pacote) pelo send_message.
