# conteudo

Publica um post por dia na @raiz.connect pela API oficial da Meta (precisa de `instagram_content_publish` no token do
cofre). Autorizado pelo Matheus em 13/10: "1 por dia, nas legendas não use emoticons".

- Agenda: `/a0/usr/conteudo/agenda.json`, só pela função `agendar()` (script `infra/operador/agendar_conteudo.py`).
- Arquivos no S3 `agentepessoal-backup-964862484412/conteudo/…` (link assinado de 1 h na hora de publicar).
- A rotina (`job_loop/_46_publicar_conteudo.py`) publica o post do dia quando chega a hora; reserva antes de falar com a
  Meta; falha antes de publicar = `falhou` + aviso "pendente:"; publicação sem confirmação = `incerta` + aviso, nunca
  repetida sozinha. Sucesso não manda aviso (decisão: celular só para lead, demo e pendente).
- Tipos (`TIPOS`): `REELS` (um .mp4, capa .jpg opcional), `IMAGE` (foto única no feed: uma .jpg, sem capa; vai à
  Meta só com `image_url` + `caption`, sem `media_type`) e `CARROSSEL` (2 a 10 .jpg). Tipo desconhecido falha, nunca
  vira carrossel. Trocar o formato de um post pendente: `trocar_formato()` (script
  `infra/operador/trocar_formato_conteudo.py`), que guarda cópia da agenda antes.
- A rotina relê o helper quando o arquivo muda e grava em `/a0/usr/conteudo/rotina.json` o pid e o sha256 do helper
  carregado de fato.
- Estados: `TRANSICOES` em `helpers/conteudo.py`; diário em `/a0/usr/conteudo/diario.jsonl`.
- **Ficha (24/10):** todo post agendado diz como refazê-lo. Post da rotina da semana: `origem.semana` (a proposta é a
  ficha). Qualquer outro leva `ficha` = {`brief` (o que é, para quem, o que diz), `fonte` (onde estão os arquivos de
  origem: repositório, branch, pasta), e se houver `titulo`, `como_refazer`, `story` (campos do kit), `spec` (ficha do
  molde do Designer), `falas` (narração do Reel com `inicio`/`fim` medidos)}; sem isso `agendar()` recusa. Post antigo
  ganha ficha por `anotar_ficha()` (script `infra/operador/ficha_conteudo.py`), que faz o Crítico julgar de novo.
  Reprovado na conferência antecipada, `semana.refazer_item` refaz sozinho story, carrossel e foto pela ficha; o que
  não se refaz (Reel agendado) vira evento do gestor, que decide (cancela e cria outro, troca, remarca). Desde 04/11
  nada disso vai ao Matheus como pergunta.
- **Fala x tela no Reel (24/10):** a narração que o Crítico recebe tem os tempos medidos no áudio do próprio vídeo
  (faster-whisper); sem ele, as `falas` da ficha; o Gemini só por último e marcado como aproximado (ele escrevia os
  segundos 4 a 6 s adiantados e reprovou o `s2-expectativa`, que estava sincronizado).

## Plano de 22/10: 4 no feed + story todo dia

Matheus, 22/10: "estamos batendo mt em reels, acho que deve ser 4 por semana, 2 carrosseis e 2 videos e story sim todo
dia". Carrossel na terça e na sexta, Reel na quarta e no domingo, às 11:45; 1 story por dia às 9h; 2 dos 4 posts falam
da gestão e 2 de custo e preço.
- Tipo `STORY` (um .jpg ou um .mp4, 1080x1920): vai à Meta com `media_type=STORIES` e `image_url`/`video_url`, sem
  legenda (a API não leva legenda, enquete, link nem música). O story tem a vaga dele: um post e um story por dia
  (`canal()`); `devido()` olha cada vaga.
- Arte do story: `helpers/story.py` desenha a partir dos layouts do kit (`story/story.html`; eram 5 até 11/11: dica, post-novo,
  video-novo, bastidor, oferta), com o navegador do container; o agente faz sozinho; desde 22/10 também o carrossel e o
  Reel, pelos moldes (`/a0/usr/moldes`, implantados com `implantar.py --moldes`; a marca raiz aplica o kit). Telas reais do sistema para o bastidor em
  `story/telas/` (telas escuras e inteiras, com o menu, de uma empresa de exemplo na cópia de teste). Regras em código: sem emoji, sem travessão, R$ só com "valores de exemplo", imagem só de arquivo local.
- `semana.propor(propostas=4, stories=7)`: o Designer desenha o feed, `story.py` os stories, o Crítico julga todos
  (tipo `story` no plugin especialistas). Reel: só prévia e narração na proposta; aprovado pelo Crítico,
  `helpers/video_fila.py` gera o vídeo em segundo plano (um por vez, voz pela credencial curta `/voz` do host) e
  `semana.concluir_video` agenda e avisa.

## Autonomia (04/11): o Crítico decide, o Matheus só é avisado

Matheus, 04/11: "Mas eu já falei que eu não quero um agente para ficar esperando eu falar. Ele tem que criar, se já tem
um crítico para ver o que passa e o que não passa, ele tem que decidir se posta, se não posta, as decisões que tem que
ser tomadas, etc., sem depender de mim." (Na semana s20261102-1 o gestor perguntou "Como seguimos?" e nada foi agendado.)
- `semana.propor`: o que o Crítico aprovou entra na agenda na mesma hora (`_decidir`, autor "gestor: o Crítico
  aprovou"); o aviso da semana sai sem botões.
- `semana.passo_autonomo` (a cada passada da conferência, na rotina `_46`, um passo por vez): a proposta reprovada é
  refeita (`REFAZER_AUTO` = 2 vezes: o Designer revisa com os motivos), depois uma ideia nova para a mesma vaga, e se
  nada passar o dia fica sem aquele post. Story que chama um post que não vai sair vira "dica". Proposta sem tempo
  (menos de `FOLGA_AUTO_MIN` antes da hora) sai da semana. Cada decisão vai ao Matheus em uma linha, sem botão.
- Sem o Crítico (plugin ausente ou sem veredito claro), nada entra sozinho.
- Semana anterior a 04/11 só entra no fluxo pelo operador: `semana.assumir(sid)` com `AUTOR["quem"] = "operador: ..."`.
- O "Publicar mesmo assim" e as perguntas do gestor saíram do caminho normal; o botão antigo e `liberar_post` /
  `aprovar_semana` continuam valendo quando é ele quem manda.
- Exceção que ainda chega a ele: publicação que falhou ou ficou incerta na Meta (login, token), que ninguém resolve sem ele.

## Gestor de conteúdo (03/11, "Age e avisa", só o Instagram)

`helpers/gestor.py`: às 08:30, 11:15 e 20:00 e quando algo é bloqueado, reprovado, não se refaz ou a publicação falha
(rotina `_46`, nunca dois juntos), o papel `gestor` do especialistas (Claude Opus 5.5) lê a agenda (7 dias para trás e
para frente), o Crítico, o diário, a semana proposta, as decisões e a oferta, e devolve ações de um vocabulário fechado.
- Pode, só no que ainda não saiu: segurar, remarcar, cancelar, trocar datas de dois pendentes do mesmo canal, mandar
  refazer (não Reel) com instrução; e, desde 04/11, criar (`semana.criar`: post ou story para dia vazio, até 2 por
  execução, Designer + Crítico; aprovado entra na agenda). Não pergunta nada ao Matheus. Sempre com motivo, tudo no
  diário. A ferramenta tem `conteudo` acao "cobrir" (o fechamento do dia usa quando falta post amanhã).
- Não pode: publicar, liberar reprovado, apagar o que saiu, dois no mesmo dia, mexer em publicando/publicada/incerta,
  mudar legenda. Ação fora disso é recusada pelo código e vai ao diário.
- Uma mensagem por execução, só quando agiu (aviso, sem botão). Teto: US$ 0,30 por execução, 10 execuções e US$ 2 por dia
  (`gestor.jsonl` guarda o custo). Modo seco: `gestor.rodar(seco=True)` decide e mostra, sem executar.

## Variedade, referências e um briefing só (11/11)

Matheus, 11/11: "Esses storys iguais só com texto diferente postados diariamente estão péssimos, zero criatividade, esse
grupo desses 3 agentes, um construtor, crítico e gerenciador, estão horríveis, não se entendem, não têm criatividade, não
buscam tendências de outros concorrentes, o próprio facebook mostra os anúncios dos concorrentes e dá pra ver o que tá
dando certo e nada disso é aproveitado, storys e feed sem graça, repetidos". Medido: 9 stories seguidos com a mesma arte
(6 eram "dica"); a rotina impunha um layout por dia da semana; story cujo post não saía virava "dica"; o Gestor
cancelava story "porque pelo plano o story de quarta chama o Reel".
- **Stories:** 14 layouts em `story/story.html`, cada um com a sua composição e o seu fundo (`story.VISUAL` diz a
  família): enquete, quiz, numero, antes-depois, conversa, checklist, tela-zoom, foto, caixinha, mais dica, post-novo,
  video-novo, bastidor e oferta. Regra em código (`semana.variedade`): layout e visual não se repetem em dias seguidos;
  em 7 dias, nenhum layout mais de 2 vezes e nenhuma família mais de 3. Conta o que saiu, o que está agendado e o que
  está sendo refeito. Vale em `propor`, `criar`, no refazer (o Designer recebe os layouts que servem ao dia) e na troca
  do story cujo post não sai (`TROCA`: um layout livre que não chama post, não mais "dica").
- **Feed:** o molde de um post dos últimos 14 dias não volta (`_moldes_vizinhos`, com os posts da mesma leva; o passeio
  pelas telas, `TOUR`, conta como um molde só); título em lista numerada ("3 sinais") só um a cada 14 dias e nenhum
  título começa como um recente (`titulo_repetido`).
- **Referências:** `concorrentes/helpers/referencias.py` monta o radar com o que a rodada semanal já guarda (anúncios
  há mais tempo no ar, posts acima da média do perfil, vídeos em alta), cada um com um id. Cada proposta declara
  `referencia` {id, o_que_muda}; cópia do gancho e nome de concorrente em texto público são recusados em código.
- **Um briefing:** `semana.briefing_comum()` (regras + radar + os últimos 14 dias da Raiz) é o texto que a rotina
  (`conteudo` acao "briefing"), o Designer, o Crítico e o Gestor recebem igual (teste
  `t_os_tres_agentes_leem_o_mesmo_briefing`).
- **Vídeos:** desde 01/11 nenhum Reel saía. Na criação, todo Reel caía no molde `lanca-app` (passeio pelas telas) e
  morria nas regras dele ou em tela que não existe; os 3 que ficaram prontos entraram na agenda pela aprovação da
  PRÉVIA e foram reprovados como vídeo pronto na conferência antecipada, sem tempo de refazer. Agora o vídeo pronto é
  julgado quando o render termina (`semana.julgar_video`): legenda que promete demais é reescrita sem renderizar de
  novo; problema no vídeo devolve a proposta ao refazer (até `MAX_RENDERS`); render que falha tenta mais uma vez; e o
  vídeo aprovado pronto não é rejulgado (`conteudo.aprovado_na_criacao`).
- **Ensaio com data simulada:** `semana.ligar_ensaio()` / `desligar_ensaio()` (só com AUTOR "operador: ...";
  `infra/operador/ensaio_conteudo.py`) deslocam o "agora" do PLANEJAMENTO (a semana que `propor` preenche, o briefing e
  a agenda que a rotina lê) por no máximo 240 min; o refazer, o Crítico, os vídeos e a publicação seguem o relógio
  real, e o aprovado entra na agenda de verdade. Não há ação nem parâmetro na ferramenta; arquivo forjado é ignorado; a
  semana fica marcada com `ensaio`.
