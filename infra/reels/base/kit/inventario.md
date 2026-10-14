# Inventário dos materiais dos carrosséis (processo do kit, etapa B)

| Arquivo | Origem | Uso | Real ou gerado |
|---|---|---|---|
| `manrope-*`, `instrument-serif-*` (+ OFL) | erp-saas `frontend/erp-saas/apps/web/public/fonts/` via kit `marketing/video-invisivel/assets/fonts/` | todo o texto | real (OFL) |
| `rc-logo-dark-v26.png`, `rc-logo-light-v26.png`, `raiz-mark.webp` | erp-saas `frontend/erp-saas/apps/web/public/` | logo do topo | real |
| `tela-calculadora.jpg` | captura da página pública raizconnect.com.br/materiais/precificacao/calculadora (430 px, 3x), 14/10/2026 | slide final (tela real do produto) | real |
| `fotos/molho-pimenta.jpg` | **gerada por IA**: Stability Stable Image Ultra (Bedrock us-west-2), semente 23, prompt "pimenta" em scratchpad `carr_img/gerar.py`; escolhida entre 11, 23 e 37 (fundo mais escuro, espaço para título) | capa do custo em 10 minutos | gerada |
| `fotos/bolo.jpg` | **gerada por IA**: Stable Image Ultra, semente 5 (entre 5 e 19: fundo verde da marca) | capa do quiz | gerada |
| `fotos/entrega.jpg` | **gerada por IA**: Stable Image Ultra, semente 7 (entre 7 e 42) | capa da polêmica | gerada |
| `fotos/produtos.jpg` | **gerada por IA** para o vídeo da oferta (erp-saas `marketing/oferta-lucro-na-mao/assets/geradas/produtos.jpg`) | capa da garantia | gerada |

Prompts das três fotos novas: produto em vidro/kraft sem texto, fundo verde-escuro, luz quente lateral, espaço vazio
em cima para o título; negativo: texto, logo, marca, pessoas, mãos, ilustração.
