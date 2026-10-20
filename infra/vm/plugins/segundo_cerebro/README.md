# segundo_cerebro

Serve a página `/segundo-cerebro` (Next standalone, `app/`) por dentro do Agent Zero, só para a sessão do Matheus.

- `extensions/python/startup_migration/_15_segundo_cerebro_gateway.py`: antes de o web app nascer, envolve
  `UiServerRuntime.create` (idempotente) para registrar o gateway como primeiro `before_request`. Nenhum arquivo do
  núcleo muda.
- `helpers/gateway.py`: decide cada pedido (sessão `authentication`/`usuario`/`user_id`, lista fechada de caminhos,
  métodos, identidade forjada), limpa os cabeçalhos e repassa ao Next. Ele se recarrega quando o arquivo muda.
- `helpers/processo.py`: o `node server.js` em `127.0.0.1`, porta efêmera, bearer interno só em memória, ambiente
  mínimo, release em `/a0/usr/segundo_cerebro/atual`.
- `hooks.py`: `install` (valida e registra), `pre_update` (para o Node), `uninstall` (para e desliga). Não há
  `execute.py`.

Contrato completo: `app/SECOND_BRAIN.md`. Implantar e reverter: `docs/SEGUNDO_CEREBRO_DEPLOY.md` (só por
`implantar.py --segundo-cerebro`). Testes: `tests/suite.py` (precisa de Flask: `/opt/venv-a0/bin/python`).
