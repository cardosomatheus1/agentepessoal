# whatsapp

Fale com o agente pelo WhatsApp: texto, **áudio** (transcrito em português), foto e arquivo. As
respostas voltam pelo WhatsApp, e ele **te avisa** quando termina algo com você longe.

```
WhatsApp → Meta → Lambda de controle (sempre no ar) → fila SQS → VM: ponte_whatsapp → este plugin → agente
agente → este plugin → ponte_whatsapp (:8789) → Meta → WhatsApp
```

- **Com a VM dormindo**: a Lambda guarda a mensagem, liga a VM e responde na hora "Acordando o agente…".
  Ao acordar, a ponte entrega o que estava na fila.
- **Uma conversa "WhatsApp" por pessoa**, visível também no app. `/nova` começa outra (a anterior vira
  conversa comum).
- **Áudio**: Whisper `small` em português, do próprio Agent Zero; a conversa mostra `🎤 texto`. Se a
  transcrição falhar, o áudio vai anexado.
- **Respostas**: a resposta final do agente vai para o WhatsApp (formatação convertida: negrito, listas,
  tabelas viram linhas). Respostas intermediárias de um `/goal` não vão.
- **Avisos** em outras conversas: se você não escreve há 5 min e o agente termina (ou para para te
  perguntar algo), chega um resumo; tarefa agendada que termina sempre avisa.
- **Arquivos**: a ferramenta `whatsapp_enviar` manda print/PDF/foto para o dono da conversa.

Segurança:
- só números cadastrados falam com o agente (os outros são ignorados na Lambda);
- o agente não vê números nem o token: pede envio por **login** e a ponte só conhece os cadastrados — não
  dá para mandar mensagem a terceiros;
- token, chave do app e números ficam no SSM (`/agentepessoal/whatsapp/config`), preenchidos pela caixa
  **WhatsApp** da página de controle;
- o webhook tem um caminho secreto e, com a chave do app salva, confere a assinatura da Meta;
- ponte ↔ plugin com chave compartilhada (`/a0/usr/whatsapp/.chave`); a porta 8789 não tem regra de
  entrada na AWS.

Fora da janela de 24 h desde a sua última mensagem, a Meta só deixa enviar **modelos aprovados**: com
`modelo_aviso` configurado (um modelo "utility" com um parâmetro), o aviso sai por ele.
