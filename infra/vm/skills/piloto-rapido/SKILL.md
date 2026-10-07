---
name: piloto-rapido
description: "Executar tarefas repetitivas no celular (jogos, muitos cliques parecidos, formulários em série) com um loop rápido: código lê a tela, o Jev decide em ~0,3 s, e o LLM só entra quando algo foge do previsto."
version: 1.0.0
tags: ["celular", "jogo", "jev", "typesafe", "automacao", "rapido", "loop"]
trigger_patterns:
  - "jogar"
  - "jogo"
  - "repetir"
  - "várias vezes"
  - "em série"
  - "piloto rápido"
---

# Piloto rápido (LLM planeja, Jev decide, código executa)

Chamar o LLM a cada passo leva 15–30 s. Para tarefas repetitivas, divida assim:

| Camada | Quem | O que faz |
|---|---|---|
| Entender e planejar | você (LLM) | Uma vez: olha a tela, entende a tarefa e escreve/escolhe o script |
| Ler e agir | código (`piloto.py`) | Lê pixels/árvore da interface, toca, desliza, confere se a tela mudou |
| Decidir cada passo | **Jev** (TypeSafe) | Recebe estado + perguntas tipadas e responde em ~0,3 s com probabilidades |
| Exceções | você (LLM) | Quando o script sai com `PRECISA_LLM: ...`, analise, corrija e rode de novo |

## Tarefas prontas

| Tarefa | Comando |
|---|---|
| Jogar 2048 | `python3 /a0/usr/skills/piloto-rapido/scripts/tarefas/jogar_2048.py 30` |

O script abre o app sozinho, imprime uma linha por jogada (decisão, tempo, placar). Se o Jev não estiver configurado, ele sai com `PRECISA_LLM: Jev indisponível`; nesse caso avise o usuário e, se ele quiser, rode com `--sem-jev` (regra simples em código).

## Criar uma tarefa nova

1. Tire um print (`acao.sh print` da skill **celular**) e entenda a tela.
2. Escreva `/a0/usr/skills/piloto-rapido/scripts/tarefas/<nome>.py` usando a biblioteca:

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from piloto import Celular, PrecisaLLM, cor_mais_proxima, escolha, sim_nao, nota, jev, rodar

def main():
    cel = Celular()
    for passo in range(20):
        tela = cel.tela()                      # tela.pixel(x, y) -> (r, g, b); tela.hash
        estado = {...}                         # o que o código consegue ler da tela
        r = jev(estado, {"acao": escolha("Qual a próxima ação?", ["tocar_ok", "rolar", "voltar"])})["acao"]
        if r["confidence"] < 0.3:
            raise PrecisaLLM(f"decisão incerta: {r['probabilities']}")
        ...                                    # cel.tocar / cel.deslizar / cel.digitar / cel.tecla
        if cel.esperar_mudar(tela.hash).hash == tela.hash:
            raise PrecisaLLM("a ação não mudou a tela")

rodar(main)
```

3. Regras de ouro:
   - Coloque no **código** tudo que é regra fixa (posições, cores, simulação do jogo, validação).
   - Use o **Jev** para julgamentos rápidos entre opções conhecidas: `escolha` (uma opção), `sim_nao` (probabilidade), `nota` (níveis ordenados). Envie no estado só o necessário (até ~32 mil tokens).
   - Levante `PrecisaLLM` sempre que algo inesperado acontecer, em vez de insistir.
   - Para ler textos e posições de botões, prefira `adb -s android:5555 shell uiautomator dump` à leitura de pixels.
4. Rode o script, acompanhe a saída e, ao terminar, mostre um print final ao usuário.

## Regras

- Nunca faça compras, pagamentos ou cadastros sem confirmação explícita do usuário — nem dentro de scripts.
- Mantenha os scripts curtos e específicos; guarde os bons em `tarefas/` para reutilizar.
