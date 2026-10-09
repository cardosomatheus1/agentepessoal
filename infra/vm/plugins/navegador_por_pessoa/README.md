# Navegador por pessoa

O plugin de navegador do Agent Zero roda um único Chromium com um único perfil (`tmp/browser/sessions/shared`)
para todas as conversas. Com dois logins (Matheus e Fernanda), isso deixava qualquer conversa usar as contas
logadas no navegador — Google, Facebook, Claude — de quem logou primeiro.

Aqui, ao criar a sessão de navegador de uma conversa, o dono da conversa (mesma regra da separação de
usuários, `login_usuarios`) escolhe o perfil:

- `DONO_DO_PERFIL_COMPARTILHADO` (matheus) continua no perfil `shared`, com os logins que já existem;
- qualquer outro login ganha um Chromium próprio em `tmp/browser/sessions/pessoa_<login>`.

Conversas sem dono identificado ficam no perfil compartilhado (as tarefas agendadas do Matheus).
