# cofre

Cofre de senhas **por pessoa**. O cofre do Agent Zero (Configurações → Secrets) é um só para todos os
logins; este separa o seu do da Fernanda.

- **Guardar**: menu lateral (⌄) → **Cofre de senhas** → nome (`FACEBOOK_SENHA`) + valor. O valor não pode
  ser lido de volta, só substituído ou apagado. Arquivo: `/a0/usr/segredos/<login>.json` (0600).
- **Usar**: o agente escreve `§§secret(FACEBOOK_SENHA)` no argumento da ferramenta (ex.: no campo de senha
  do navegador). Logo antes de executar, depois do revisor de aprovações (que só vê o nome), o nome vira
  o valor do **dono da conversa**. Se o valor aparecer num resultado, volta mascarado. O modelo nunca vê.
- O prompt do agente lista só os **nomes** disponíveis e manda nunca pedir senha na conversa.
- **Códigos de uso único** (2FA, SMS, e-mail): a ferramenta `pedir_codigo` (plugin `whatsapp`) manda
  "🔑 Preciso de um código" no seu WhatsApp e espera até 10 min; a próxima mensagem curta com números que
  você mandar vai direto para a conversa que pediu.
