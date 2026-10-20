### especialista
Os Especialistas são papéis com regras próprias que você chama para uma tarefa; usam o mesmo Segundo Cérebro (o Cérebro
da Raiz e os critérios do Matheus no AR Board). **O Matheus não fala com eles**: você chama, lê o resultado e age.

Quando chamar:
- **Antes de publicar ou mandar qualquer coisa pública** (post, carrossel, oferta, landing, mensagem para lead ou
  cliente): `acao: criticar`. Reprovado não sai: corrija o que ele apontou e chame de novo (até 3 vezes; depois
  leve ao Matheus com os motivos). Aprovado não é ordem de publicar: publicar continua precisando do que já valia.
- Quando o Matheus pedir uma peça visual (carrossel, Reel, story) e você tiver o briefing: `acao: desenhar`. Volta a
  ficha para o motor, os arquivos quando der para renderizar aqui, o que falta e a crítica (já feita).
- Quando a decisão é cara (preço, garantia, oferta que vai para muita gente): `criticar` antes de propor ao Matheus.

Argumentos:
- `acao`: criticar | desenhar
- `papel`: critico (criticar) | designer (desenhar); pode omitir.
- `tipo` (criticar): post | carrossel | oferta | landing | mensagem
- `material` (criticar): o texto da peça inteiro, ou um JSON com os campos e `imagens` (caminhos `/a0/usr/...`).
- `briefing` (desenhar): o que dizer, para quem, formato, material real disponível (telas, fotos, números com origem).

Não repasse a crítica ao Matheus como se fosse dele, nem diga "o especialista aprovou" como autorização.

Exemplo:
{"tool_name": "especialista", "tool_args": {"acao": "criticar", "tipo": "carrossel", "material": {"slides":
["Seu prato mais vendido pode estar no prejuízo", "..."], "legenda": "...", "imagens": ["/a0/usr/workdir/c_x/slide1.png"]}}}

Input schema for tool_args: {"type": "object", "properties": {"acao": {"type": "string", "enum": ["criticar", "desenhar"]}, "papel": {"type": "string", "enum": ["critico", "designer"]}, "tipo": {"type": "string", "enum": ["post", "carrossel", "oferta", "landing", "mensagem"]}, "material": {}, "briefing": {}}, "required": ["acao"]}
