# App — interface estilo Grok

Next.js (PWA) com chat em streaming usando modelos da OpenAI servidos pelo **Amazon Bedrock** (API Converse).

```bash
npm install
npm run dev        # http://localhost:3000
```

Precisa de credenciais AWS com acesso ao Bedrock em `us-east-1` (variáveis padrão da AWS ou role IAM).

| Modo | Modelo (Bedrock) |
|---|---|
| Rápido (padrão) | `us.openai.gpt-6-luna` |
| Avançado | `us.openai.gpt-6.1-sol` |

Para trocar de modelo, basta mudar o ID em `lib/models.ts`.

Estrutura:

- `lib/chat.ts` — chamada ao modelo em streaming (Bedrock ConverseStream) (vira a Lambda de chat na fase 1 da AWS).
- `app/api/chat/route.ts` — endpoint que transmite eventos NDJSON (`thinking`, `text`, `done`, `error`).
- `components/` — interface (barra lateral, campo de mensagem, mensagens, bloco "Pensando").
- `lib/store.ts` — histórico no navegador (temporário; vai para o DynamoDB).

Ainda **sem login**: não publicar antes de adicionar autenticação.
