---
name: piloto-rapido
description: "Fazer sozinho tarefas no celular que exigem muitas decisões rápidas (jogos por turno como xadrez, damas, 2048, sudoku; apps com muitos passos parecidos). Você planeja uma vez e escreve um script; o código lê a tela, o Jev decide cada passo em ~0,3 s, e você só volta quando o script pedir."
version: 2.0.0
tags: ["celular", "jogo", "xadrez", "jev", "typesafe", "automacao", "rapido", "loop", "autonomo"]
trigger_patterns:
  - "jogar"
  - "jogue"
  - "jogo"
  - "partida"
  - "xadrez"
  - "repetir"
  - "várias vezes"
  - "em série"
  - "piloto rápido"
---

# Piloto rápido — você decide sozinho como fazer

Você (LLM) é lento para decidir cada passo (15–30 s). Para tarefas com muitas decisões, **não jogue/clique passo a passo pelo chat**. Em vez disso:

1. **Entenda** a tarefa e a tela (poucos passos manuais).
2. **Escreva um script** que faz o loop sozinho: lê a tela → monta o estado → pergunta ao **Jev** → age → confere.
3. **Rode**. O script só devolve o controle quando algo foge do previsto (`PRECISA_LLM: motivo`).
4. **Corrija e continue** a partir do motivo. **Guarde** o script bom para a próxima vez.

Ninguém vai te dizer qual app usar, onde fica cada coisa ou qual estratégia seguir: descubra, decida e explique ao usuário em 2–3 linhas o que escolheu.

## Passo 0 — já existe?

Veja `/a0/usr/skills/piloto-rapido/scripts/tarefas/README.md`. Se já há um script para a tarefa, rode-o direto.

## Passo 1 — explorar (use a skill **celular**)

- Apps instalados: `adb -s android:5555 shell pm list packages -3`. Se faltar um app, instale (F-Droid: `curl -sL https://f-droid.org/api/v1/packages/<pacote>` dá a versão; APK em `https://f-droid.org/repo/<pacote>_<versão>.apk`; ou Play Store/Aurora Store).
- Abra o app (`acao.sh abrir <pacote>`), tire print (`acao.sh print` + `vision_load`) e resolva diálogos iniciais (boas-vindas, permissões, "novidades").
- Descubra **como ler o estado** sem visão do LLM:
  - Apps comuns: `cel.elementos()` (textos, botões e posições da interface).
  - Jogos desenhados como imagem: localize a área (ex.: tabuleiro) no print e use `tela.grade(x1, y1, x2, y2, linhas, colunas)` — cada célula traz cor média e `variacao` (alta = tem peça/desenho; baixa = vazia). Calibre olhando os números de 1–2 telas.
- Descubra **como agir**: tocar origem → destino, deslizar, tocar botão por texto.

## Passo 2 — escrever o script

Crie `/a0/usr/skills/piloto-rapido/scripts/tarefas/<nome>.py`:

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from piloto import Celular, PrecisaLLM, escolha, sim_nao, nota, jev, rodar

def main():
    cel = Celular()
    cel.abrir("<pacote>")
    for passo in range(200):
        tela = cel.esperar_estavel()                 # espera animações / o adversário
        estado = ...                                  # do código: grade, elementos, regras
        opcoes = {...}                                # rótulo -> descrição curta (só ações válidas!)
        r = jev({"objetivo": "...", "estado": estado}, {"acao": escolha("Qual a melhor próxima ação?", opcoes)})["acao"]
        ...                                           # executar r["choice"]
        if cel.esperar_mudar(tela.hash).hash == tela.hash:
            raise PrecisaLLM(f"'{r['choice']}' não mudou a tela")
        print(f"passo {passo}: {r['choice']} (confiança {r['confidence']:.2f})", flush=True)

rodar(main)
```

Divisão de trabalho dentro do script:

| O quê | Quem |
|---|---|
| Regras fixas: ler a tela, listar ações válidas, simular, validar, detectar o fim | **código** |
| Julgamento entre opções válidas (melhor lance, melhor botão, "isso combina?") | **Jev**: `escolha(instr, opcoes)`, `sim_nao(instr)`, `nota(instr, niveis)` — ~0,3 s, até ~32 mil tokens de estado |
| Situação inesperada, tela desconhecida, Jev inseguro, ação sem efeito, passo irreversível | **você**: `raise PrecisaLLM("...")` |

Boas práticas:
- Dê ao Jev **só opções válidas** e, para cada uma, as consequências que o código consegue calcular (pontos, risco, o que muda). Peça a ele o julgamento; não peça para ele descobrir regras.
- Jogos com regras conhecidas: use uma biblioteca de regras em vez de visão. Já disponível: **python-chess** (`import chess`) para xadrez — dá lances legais, simula lances, detecta xeque/mate e permite descobrir o lance do adversário comparando a ocupação das casas antes/depois com os lances legais.
- Se houver adversário (computador), espere a tela estabilizar e identifique o lance dele antes de decidir o seu.
- Imprima uma linha curta por passo (o usuário acompanha) e um resumo no fim.

## Passo 3 — rodar, acompanhar, corrigir

- Teste com poucos passos primeiro (`python3 script.py` com um limite pequeno). Funcionou? Rode a tarefa completa.
- Saiu com `PRECISA_LLM: ...`? Olhe um print, entenda, ajuste o script (ou resolva a tela à mão com a skill **celular**) e rode de novo — o script deve conseguir **retomar do estado atual da tela**.
- Mais de 3 correções seguidas sem progresso: pare e explique ao usuário o que está bloqueando.
- O usuário pode assistir ao vivo pelo **Ver celular** da página de controle.

## Passo 4 — guardar

Ao terminar, registre em `tarefas/README.md`: nome do script, o que faz, app/pacote, como rodar e limitações conhecidas.

## Regras

- Nunca faça compras, pagamentos, cadastros, envios ou aceite termos sem confirmação explícita do usuário — nem dentro de scripts (use `PrecisaLLM` antes do passo irreversível).
- Não faça login em contas do usuário; peça que ele faça pelo **Ver celular**.
