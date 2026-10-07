# App — interface estilo Grok

Next.js (PWA) com chat em streaming usando Claude no AWS Bedrock.

```bash
npm install
npm run dev        # http://localhost:3000
```

Precisa de credenciais AWS com acesso ao Bedrock em `us-east-1` (variáveis padrão da AWS ou role).

| Modo | Modelo (Bedrock) | Raciocínio |
|---|---|---|
| Rápido | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | desligado |
| Padrão | `us.anthropic.claude-sonnet-5-5` | adaptativo, effort `medium` |
| Power | `us.anthropic.claude-opus-5-5` | adaptativo, effort `high` |

Estrutura:

- `lib/chat.ts` — chamada ao Claude em streaming (vira a Lambda de chat na fase 1 da AWS).
- `app/api/chat/route.ts` — endpoint que transmite eventos NDJSON (`thinking`, `text`, `done`, `error`).
- `components/` — interface (barra lateral, campo de mensagem, mensagens, bloco "Pensando").
- `lib/store.ts` — histórico no navegador (temporário; vai para o DynamoDB).

Ainda **sem login**: não publicar antes de adicionar autenticação.
