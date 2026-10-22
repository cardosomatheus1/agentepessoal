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

## Plano de 22/10: 4 no feed + story todo dia

Matheus, 22/10: "estamos batendo mt em reels, acho que deve ser 4 por semana, 2 carrosseis e 2 videos e story sim todo
dia". Carrossel na terça e na sexta, Reel na quarta e no domingo, às 11:45; 1 story por dia às 9h; 2 dos 4 posts falam
da gestão e 2 de custo e preço.
- Tipo `STORY` (um .jpg ou um .mp4, 1080x1920): vai à Meta com `media_type=STORIES` e `image_url`/`video_url`, sem
  legenda (a API não leva legenda, enquete, link nem música). O story tem a vaga dele: um post e um story por dia
  (`canal()`); `devido()` olha cada vaga.
- Arte do story: `helpers/story.py` desenha a partir de 5 layouts fixos do kit (`story/story.html`: dica, post-novo,
  video-novo, bastidor, oferta), com o navegador do container; o agente faz sozinho; desde 22/10 também o carrossel e o
  Reel, pelos moldes (`/a0/usr/moldes`, implantados com `implantar.py --moldes`; a marca raiz aplica o kit). Telas reais do sistema para o bastidor em
  `story/telas/` (telas escuras e inteiras, com o menu, de uma empresa de exemplo na cópia de teste). Regras em código: sem emoji, sem travessão, R$ só com "valores de exemplo", imagem só de arquivo local.
- `semana.propor(propostas=4, stories=7)`: o Designer desenha o feed, `story.py` os stories, o Crítico julga todos
  (tipo `story` no plugin especialistas) e vai uma mensagem com os 11. Reel: só prévia e narração na proposta
  (decisão #39); aprovado, `helpers/video_fila.py` gera o vídeo em segundo plano (um por vez, voz pela credencial curta
  `/voz` do host) e `semana.concluir_video` agenda e avisa.
