### celular
Controla o celular Android virtual do usuário (720x1280) em **um passo**: faz a ação, espera a tela parar de mexer e devolve o texto da tela (botões, textos e campos com a posição de cada um), se a tela mudou e o app aberto. Quando a tela quase não tem texto (jogo, foto, vídeo) uma imagem pequena da tela vem anexada automaticamente.
Use esta ferramenta para tudo no celular — não use adb pelo terminal nem `vision_load` para olhar o celular. Decida pelo texto; peça `imagem: true` só quando precisar ver algo visual.
Ações (`acao`): `ver`, `tocar` (x, y), `tocar_texto` (texto), `tocar_longo` (x, y), `deslizar` (direcao: cima|baixo|esquerda|direita — sentido do dedo; ou x1,y1,x2,y2), `digitar` (texto; `enviar: true` aperta Enter; `acrescentar: true` não apaga o que já está no campo), `voltar`, `inicio`, `enter`, `apagar`, `abrir` (pacote), `esperar` (segundos).
Se vier "NÃO MUDOU", a ação não fez efeito: escolha outra, não repita igual. Para muitos passos repetidos (jogos), use a skill piloto-rapido.
Nunca faça compras, envios, cadastros ou aceite termos sem confirmação do usuário. Diga ao usuário: "acompanhe no botão **Celular**".
Input schema for tool_args: {"type": "object", "properties": {"acao": {"type": "string", "enum": ["ver", "tocar", "tocar_texto", "tocar_longo", "deslizar", "digitar", "voltar", "inicio", "enter", "apagar", "abrir", "esperar"]}, "x": {"type": "integer"}, "y": {"type": "integer"}, "x1": {"type": "integer"}, "y1": {"type": "integer"}, "x2": {"type": "integer"}, "y2": {"type": "integer"}, "texto": {"type": "string"}, "direcao": {"type": "string", "enum": ["cima", "baixo", "esquerda", "direita"]}, "pacote": {"type": "string"}, "segundos": {"type": "number"}, "enviar": {"type": "boolean"}, "acrescentar": {"type": "boolean"}, "imagem": {"type": "string", "enum": ["auto", "true", "false"]}}, "required": ["acao"]}
usage:
~~~json
{
    "thoughts": ["Vou tocar em Entrar."],
    "headline": "Tocando em Entrar no celular",
    "tool_name": "celular",
    "tool_args": {"acao": "tocar_texto", "texto": "Entrar"}
}
~~~
