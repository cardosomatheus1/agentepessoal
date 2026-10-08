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
