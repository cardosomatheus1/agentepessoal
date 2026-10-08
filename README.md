# agentepessoal

Configuração para rodar o [Agent Zero](https://github.com/agent0ai/agent-zero) com modelos da **OpenAI servidos pelo AWS Bedrock** (GPT-6.1 Sol e GPT-6 Luna).

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
| Default | GPT-6 Luna | GPT-6 Luna |
| Sol | GPT-6.1 Sol | GPT-6 Luna |

Os dois usam o endpoint compatível com OpenAI do Bedrock (`bedrock-mantle.us-east-1.api.aws/openai/v1`, API Responses).
Embeddings (memória): `sentence-transformers/all-MiniLM-L6-v2`, roda localmente, sem custo.

## Credenciais

- **Claude Code na web**: o proxy do ambiente injeta a credencial do Bedrock; não precisa de nada.
- **Outro lugar**: exporte `AWS_BEARER_TOKEN_BEDROCK` (chave de API do Bedrock) e `AWS_REGION=us-east-1` antes do `./setup.sh`.
