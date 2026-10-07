# agentepessoal

Configuração para rodar o [Agent Zero](https://github.com/agent0ai/agent-zero) com modelos da **OpenAI servidos pelo AWS Bedrock** (Claude continua como opção).

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
| Default | GPT-5.6 Terra | GPT-5.6 Luna |
| Economico | gpt-oss-120b | gpt-oss-20b |
| Power | GPT-5.6 Sol | GPT-5.6 Luna |
| Claude | Claude Sonnet 5.5 | Claude Haiku 4.5 |

Os GPT-5.6 usam o endpoint OpenAI-compatível do Bedrock (`bedrock-mantle.us-east-1.api.aws/openai/v1`, API Responses).
Embeddings: `sentence-transformers/all-MiniLM-L6-v2` local (sem custo).

## Credenciais

- **Claude Code na web**: o proxy do ambiente injeta a credencial do Bedrock; não precisa de nada.
- **Outro lugar**: exporte `AWS_BEARER_TOKEN_BEDROCK` (chave de API do Bedrock) e `AWS_REGION=us-east-1` antes do `./setup.sh`.
