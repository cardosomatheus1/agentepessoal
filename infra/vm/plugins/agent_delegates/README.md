# Delegação textual Hermes / OpenClaw

Plugin local do Agent Zero que expõe `text_delegate` para uma análise textual pontual em Hermes ou OpenClaw. O Agent Zero continua responsável por escopo, autorizações e revisão.

- Usa somente wrappers locais em `/a0/usr/workdir/agentes/bin/`.
- Hermes: adaptador one-shot validado, zero toolsets e uma iteração.
- OpenClaw: `agent exec` em workspace smoke isolado, sem ativar code mode; requer envelope JSON sem chamadas bridge.
- Não disponibiliza filesystem, navegador, ferramentas, contas, serviços ou subdelegação.
- Limites: 10.000 caracteres de entrada, 65.536 bytes de stdout e até 110 segundos.
- Não inclua senhas, tokens, códigos de autenticação ou dados pessoais desnecessários.

Para usar no Agent Zero, peça uma análise delimitada e informe `engine` e `task` à ferramenta `text_delegate`. O resultado é apenas texto não confiável para o Agent Zero revisar.
