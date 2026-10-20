# Conectores por pessoa

Os servidores MCP do Agent Zero são globais, mas cada conector entra numa conta pessoal (o Google do
Matheus, por exemplo). `donos.json` diz de quem é cada servidor (`{"<servidor>": "<login>"}`); uma
ferramenta `<servidor>.<ação>` só roda em conversas dessa pessoa. Servidor fora da lista: livre.

Os conectores começam só leitura (`--read-only`); ações que escrevem passam pelo revisor de aprovações.

`mcp_servers.json` é o valor de "MCP Servers" nas configurações do Agent Zero (aplicado pela API de
configurações). O Google usa o `workspace-mcp` instalado em `/a0/usr/mcp/venv-google`, rodando sempre (serviço
`agentepessoal-google-mcp`, HTTP em 127.0.0.1:8765 dentro do contêiner; ver `setup.sh`). Em stdio o Agent Zero
sobe o servidor a cada chamada, e o retorno do login do Google (`localhost:8765/oauth2callback`) não achava ninguém;
o cliente OAuth fica em `/a0/usr/mcp/google/client_secret.json` e o login em `/a0/usr/mcp/google/credenciais`,
fora do git. Para autorizar, a primeira chamada devolve um link do Google: o agente abre no navegador e
aceita com a conta do dono.

## Ferramentas dos conectores sob demanda (20/10)

Medido numa conversa do Matheus: 139 ferramentas nativas, 176 mil caracteres em toda chamada; 59 do Google (122 mil)
e 28 do GitHub (33 mil). Nos 14 dias antes, as conversas dele usaram 30 delas.

| Arquivo | O que faz |
|---|---|
| `helpers/sob_demanda.py` | quais vão: `SEMPRE` (Gmail buscar/ler, Agenda ler, Drive/Docs/Planilhas ler e criar o básico, login), `GITHUB_CODIGO` (em conversa que fala de código) e as ativadas na conversa; esquema mais curto (primeira frase de cada descrição, sem o e-mail repetido) |
| `extensions/python/chat_model_call_before/_40_ferramentas_do_conector.py` | aplica isso à lista de cada chamada; conector de outra pessoa nem vai |
| `tools/conector.py` | `conector` acao listar / ativar / descrever: nada deixa de ser possível |
| `extensions/python/tool_execute_before/_05_conector_ativo.py` | ferramenta do conector que rodou pelo nome fica na lista da conversa |

Medido na VM (20/10, lista montada sem chamar o modelo): conversa comum 176.491 → 38.811 caracteres (71 ferramentas);
conversa de código 46.123; convidado 22.872. As ativadas ficam em `conectores_ativas` nos dados da conversa.

**Desligar sem implantar:** criar `/a0/usr/plugins/conectores/sob_demanda_desligado` (no contêiner) volta a lista
inteira; apagar o arquivo liga de novo.
