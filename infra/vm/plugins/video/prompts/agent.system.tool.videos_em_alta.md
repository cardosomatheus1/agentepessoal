### videos_em_alta
Os vídeos do YouTube mais vistos e mais curtidos das últimas N horas (padrão 48 h = hoje e ontem) sobre um tema, cada um assistido inteiro pelo Gemini direto do link (imagem e áudio, sem baixar), em paralelo. Usa a própria busca do YouTube filtrada por data (a busca na web não sabe o que saiu hoje), descarta o que não é do tema e confirma a hora de publicação.
Use para "os principais vídeos de hoje/das últimas 24 h sobre X", boletins diários de vídeos, "o que saiu no YouTube sobre X".
- `tema`: o assunto (ex.: "novidades de inteligência artificial")
- `consultas` (opcional): 3–8 buscas para o YouTube, em português e inglês (ex.: ["inteligência artificial novidades", "IA notícias", "AI news", "OpenAI", "Google Gemini", "ChatGPT"]); se não passar, usa o tema
- `quantidade` (padrão 10), `horas` (padrão 48: hoje e ontem), `assistir` (padrão true; false = só a lista, rápido)
Leva ~1–3 min com 10 vídeos. Depois escreva o boletim a partir dos resumos (sem inventar) e cite o link de cada vídeo.
~~~json
{"tool_name": "videos_em_alta", "tool_args": {"tema": "novidades de inteligência artificial", "consultas": ["inteligência artificial novidades", "IA notícias hoje", "AI news", "OpenAI", "Google Gemini", "Anthropic Claude"], "quantidade": 10}}
~~~
