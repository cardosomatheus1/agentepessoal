# Navegador rápido

Correções aplicadas em tempo de execução no navegador embutido do Agent Zero (`plugins/_browser`), sem editar os arquivos dele:

| Problema | Efeito | Correção |
|---|---|---|
| Antes de cada chamada ao modelo o agente lê a página inteira; o script verificava o estilo de todos os ancestrais de cada elemento | ~6 s por passo numa página grande (Wikipedia) | verificação memorizada durante a leitura — mesmo resultado, 3–6× mais rápido |
| O texto da página inteira ia no prompt a cada passo (até ~65 mil tokens) | passos lentos e caros | limite de 20 mil caracteres (~5 mil tokens), com aviso ensinando a ler o resto (`content` com `selector`) |
| Voltar/Avançar esperavam um evento que não vem quando a página sai do cache | 10 s perdidos e "falhou", o agente repetia | espera só a navegação confirmar |
| Clique que abre outra página dava "click failed" | o agente repetia o passo | tratado como sucesso |

Se o Agent Zero mudar os scripts, a correção de leitura se desliga sozinha (mensagem `navegador_rapido:` no log) e o resto continua.

## Enxergar a tela (21/10)

No login da 99Food o agente errou três vezes seguidas:
- digitou a senha num campo escondido;
- tentou clicar num "Entrar" que não estava habilitado;
- não conseguiu abrir um menu sem ref.

Em nenhuma delas olhou a tela: o navegador salva um print a cada passo, mas o modelo só lê o texto da página.

| Problema | Correção |
|---|---|
| Seletor de campo (`input[type=password]`) pegava o primeiro, mesmo escondido | se o primeiro campo/botão encontrado está escondido e há outro visível, usa o visível (`correcoes.py`, correção 4) |
| O modelo agia às cegas | depois de cada ação que muda a página (clicar, digitar, abrir, voltar…), o print entra no histórico como imagem, com o que conferir e como clicar pelas coordenadas; só o último fica, os anteriores viram uma linha (`helpers/ver_tela.py`) |
