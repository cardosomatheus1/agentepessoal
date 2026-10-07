#!/usr/bin/env bash
# Instala e sobe o Agent Zero usando Claude via AWS Bedrock.
# Uso: ./setup.sh            (instala se preciso e sobe em http://localhost:50001)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
A0_DIR="${A0_DIR:-$HOME/src/agent-zero}"
PORT="${PORT:-50001}"

if [ ! -d "$A0_DIR/.git" ]; then
  git clone --depth 1 https://github.com/agent0ai/agent-zero.git "$A0_DIR"
fi

if [ ! -x "$A0_DIR/.venv/bin/python" ]; then
  uv venv -p 3.12 "$A0_DIR/.venv"
  UV_HTTP_TIMEOUT=300 uv pip install -p "$A0_DIR/.venv/bin/python" -r "$A0_DIR/requirements.txt" \
    --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cpu
fi

# Presets de modelo (Bedrock) e execução de código no shell local
mkdir -p "$A0_DIR/usr/plugins/_model_config" "$A0_DIR/usr/plugins/_code_execution"
cp "$HERE/config/presets.yaml" "$A0_DIR/usr/plugins/_model_config/presets.yaml"
cp "$HERE/config/code_execution.json" "$A0_DIR/usr/plugins/_code_execution/config.json"

# Chave do Bedrock: usa AWS_BEARER_TOKEN_BEDROCK se existir; senão um placeholder
# (no Claude Code na web o proxy injeta a credencial real).
touch "$A0_DIR/usr/.env"
if ! grep -q '^API_KEY_BEDROCK=' "$A0_DIR/usr/.env"; then
  echo "API_KEY_BEDROCK=${AWS_BEARER_TOKEN_BEDROCK:-proxy-injected}" >> "$A0_DIR/usr/.env"
fi
export AWS_REGION="${AWS_REGION:-us-east-1}"

# O modo "dockerized" faz o agente executar código neste próprio ambiente
# (sem precisar de um segundo container via RFC); ele espera o código em /a0.
[ -e /a0 ] || ln -s "$A0_DIR" /a0

cd /a0
exec .venv/bin/python run_ui.py --port="$PORT" --dockerized=true
