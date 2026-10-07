# agentepessoal

Configuração para rodar o [Agent Zero](https://github.com/agent0ai/agent-zero) com modelos Claude via **AWS Bedrock**.

## Rodar

```bash
./setup.sh
```

Abre em http://localhost:50001.

> ⚠️ O modo `--dockerized=true` faz o agente executar comandos **direto na máquina onde roda**.
> Use só em ambiente isolado (container/VM), nunca no seu computador pessoal.

## Presets (`config/presets.yaml`)

| Preset | Modelo principal | Modelo utilitário |
| --- | --- | --- |
| Default | `us.anthropic.claude-sonnet-5-5` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Power | `us.anthropic.claude-opus-5-5` | `us.anthropic.claude-sonnet-5-5` |
| Efficiency | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |

Embeddings: `sentence-transformers/all-MiniLM-L6-v2` local (sem custo).

## Credenciais

- **Claude Code na web**: o proxy do ambiente injeta a credencial do Bedrock; não precisa de nada.
- **Outro lugar**: exporte `AWS_BEARER_TOKEN_BEDROCK` (chave de API do Bedrock) e `AWS_REGION=us-east-1` antes do `./setup.sh`.
