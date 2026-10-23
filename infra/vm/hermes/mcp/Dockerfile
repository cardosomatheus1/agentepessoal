# Conectores (MCP) do Hermes num container ao lado dele (migração, fase 3): o Google (workspace-mcp, a mesma versão e as
# mesmas dependências do A0, versoes.txt) e um repasse para o MCP do GitHub que põe o token na chamada. As credenciais
# ficam SÓ aqui: o Hermes fala com este container pela rede "hermes" e nunca vê token nenhum (como o proxy do modelo).
FROM python:3.12.8-slim
COPY versoes.txt /tmp/versoes.txt
RUN pip install --no-cache-dir -c /tmp/versoes.txt workspace-mcp==2.0.1 && command -v workspace-mcp
COPY github_repasse.py /opt/github_repasse.py
