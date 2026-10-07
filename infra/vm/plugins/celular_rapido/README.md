# Celular rápido

Ferramenta `celular` para o Agent Zero: **uma ação por passo**, com a resposta já trazendo a tela.

| | Antes (adb + print + vision_load) | Agora (`celular`) |
|---|---|---|
| Ler a árvore da tela | `uiautomator dump`: 2,1 s | servidor uiautomator2 permanente: 0,07 s |
| Ver a tela | 3 passos do agente (ação, print, `vision_load`) | 1 passo: texto + imagem pequena (360 px, ~10 KB) quando a tela não tem texto ou quando pedido |
| Deslizar | — | `input swipe` (0,2 s; o `swipe` do uiautomator2 levava 2 s) |
| Esperar a tela parar | tempo fixo | compara árvore + miniatura 36×64 a cada ~0,3 s (máx. 2 s) |

Cada ação leva ~1,4–2,8 s na ferramenta (inclui as animações do Android). A tarefa "abrir o 2048, jogar para a esquerda e dizer o que mudou" levou 13,6 s no total.

O uiautomator2 é instalado no contêiner por `agent_tools.sh` (venv do servidor e `/opt/venv` dos scripts); `piloto.py` também usa ele quando disponível.
