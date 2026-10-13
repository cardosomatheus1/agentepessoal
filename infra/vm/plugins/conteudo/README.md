# conteudo

Publica um post por dia na @raiz.connect pela API oficial da Meta (precisa de `instagram_content_publish` no token do
cofre). Autorizado pelo Matheus em 13/10: "1 por dia, nas legendas não use emoticons".

- Agenda: `/a0/usr/conteudo/agenda.json`, só pela função `agendar()` (script `infra/operador/agendar_conteudo.py`).
- Arquivos no S3 `agentepessoal-backup-964862484412/conteudo/…` (link assinado de 1 h na hora de publicar).
- A rotina (`job_loop/_46_publicar_conteudo.py`) publica o post do dia quando chega a hora; reserva antes de falar com a
  Meta; falha antes de publicar = `falhou` + aviso "pendente:"; publicação sem confirmação = `incerta` + aviso, nunca
  repetida sozinha. Sucesso não manda aviso (decisão: celular só para lead, demo e pendente).
- Estados: `TRANSICOES` em `helpers/conteudo.py`; diário em `/a0/usr/conteudo/diario.jsonl`.
