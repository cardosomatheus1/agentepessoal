### assistir_video
Assiste um vídeo de verdade, inteiro, imagem e áudio, descrevendo em ordem com os tempos. YouTube: o Gemini assiste direto do link, sem baixar nada. Instagram, TikTok, X, Facebook ou arquivo local: baixa e o Pegasus (TwelveLabs) assiste.
Use SEMPRE que o usuário mandar um link ou arquivo de vídeo e pedir para ver, assistir, resumir ou analisar. Não tente assistir pelo navegador: ele não toca esses vídeos (erro no player / tela preta).
- `url`: link do vídeo; ou `caminho`: arquivo de vídeo já no disco (ex.: anexo da conversa)
- `pergunta` (opcional): o que o usuário quer saber do vídeo
- `modo` (opcional): padrão = assiste inteiro, imagem e áudio (YouTube: Gemini direto do link, sem baixar; Instagram/TikTok/arquivo: Pegasus); `"rapido"` = só lê as legendas, em segundos
~~~json
{"tool_name": "assistir_video", "tool_args": {"url": "https://www.instagram.com/p/...", "pergunta": "Que ferramentas ele mostra?"}}
~~~
