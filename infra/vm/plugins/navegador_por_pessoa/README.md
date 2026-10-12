# Navegador por pessoa

O plugin de navegador do Agent Zero roda um único Chromium com um único perfil (`tmp/browser/sessions/shared`)
para todas as conversas. Com dois logins (Matheus e Fernanda), isso deixava qualquer conversa usar as contas
logadas no navegador — Google, Facebook, Claude — de quem logou primeiro.

Aqui, ao criar a sessão de navegador de uma conversa, o dono da conversa (mesma regra da separação de
usuários, `login_usuarios`) escolhe o perfil:

- `DONO_DO_PERFIL_COMPARTILHADO` (matheus) continua no perfil `shared`, com os logins que já existem;
- qualquer outro login ganha um Chromium próprio em `tmp/browser/sessions/pessoa_<login>`.

Conversas sem dono identificado ficam no perfil compartilhado (as tarefas agendadas do Matheus).

## Perfis fora do contêiner (revisão de 12/10)

Os perfis (com os logins do Instagram, Google e Meta) ficavam em `/a0/tmp/browser/sessions`, dentro da camada do
próprio contêiner: recriar o contêiner deslogaria o agente de tudo. Agora a pasta é um atalho para
`/a0/usr/navegador/sessions` (disco da VM, no snapshot diário; fora do backup de hora em hora no S3, que ela
inundaria). Ao iniciar, o plugin liga o atalho se a cópia existir e nenhum Chromium estiver com o perfil aberto; a
pasta que estava no caminho fica ao lado (`sessions.antes-*`), nunca é apagada. A mudança inicial foi feita com
`infra/operador/mover_perfis_navegador.py` (para o contêiner, copia, inicia).
