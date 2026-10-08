### assistir_video
Assiste um vídeo de verdade: baixa (link do Instagram, YouTube, TikTok, X, Facebook… ou arquivo local) e um modelo de vídeo assiste ele inteiro, imagem e áudio, descrevendo em ordem com os tempos; junto vem a transcrição exata da fala.
Use SEMPRE que o usuário mandar um link ou arquivo de vídeo e pedir para ver, assistir, resumir ou analisar. Não tente assistir pelo navegador: ele não toca esses vídeos (erro no player / tela preta).
- `url`: link do vídeo; ou `caminho`: arquivo de vídeo já no disco (ex.: anexo da conversa)
- `pergunta` (opcional): o que o usuário quer saber do vídeo
~~~json
{"tool_name": "assistir_video", "tool_args": {"url": "https://www.instagram.com/p/...", "pergunta": "Que ferramentas ele mostra?"}}
~~~
