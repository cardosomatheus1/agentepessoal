# Criador de vídeos do NEXOS — pacote para o orquestrador (Main Opus NEXOS)

Decidido com o Matheus em 21/10/2026 (grilling, 16 perguntas, todas fechadas; fala dele: "Tudo ok", "Cria como
storys no nexos, inclusive no linear ... detalhar td, fornecer link, motor e etc, td q ele precisa pra fazer
corretamente"). Este arquivo é **insumo**: as Story Cards, os ids, o encaixe nos bounded contexts, eventos, ADRs e o
espelho no Linear são feitos pelo orquestrador do NEXOS pelas regras do repositório dele (STORY_CARD_STANDARD,
`build_state.py`, `/sync-linear`). Nada aqui autoriza pular gate, piloto ou ação governada.

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
commit `c3e618c37da2d526a09181d9c5f07e7fb1bfb0b2`, pasta `infra/reels/moldes/`.
https://github.com/cardosomatheus1/agentepessoal/tree/c3e618c37da2d526a09181d9c5f07e7fb1bfb0b2/infra/reels/moldes

Pacotes prontos (mesma conta AWS do NEXOS):
- `s3://agentepessoal-backup-964862484412/nexos/criador-videos/moldes-codigo-c3e618c.tgz` (34 MB; `infra/reels/moldes`
  versionado + `docs/MOLDES_VIDEO.md` + `calibracao/moldes` + `GLOSSARY.md`; sha256 começa com `8e18e79d6c347081`).
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
- **Voz**: Amazon Nova 2 Sonic, voz Carolina (`motor/voz_sonic.mjs`). O texto antigo cita Polly; vale Sonic.
- **Licenças**: músicas só CC0 (`motor/musica/licencas.json`), fontes só OFL (`motor/fontes`), filmagens geradas por nós.

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
30 Moldes novos, ainda sem julgamento; vale Q13).

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
