"""Joga 2048 no celular: código lê o tabuleiro e simula jogadas; o Jev escolhe; o LLM só entra se algo fugir do previsto.

Uso: python3 jogar_2048.py [jogadas=30] [--sem-jev]
   --sem-jev: decide por uma regra simples em código (para testar sem a chave do Jev).
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from piloto import Celular, PrecisaLLM, cor_mais_proxima, escolha, jev, rodar  # noqa: E402

# Geometria do app com.uberspot.a2048 numa tela 720x1280 (cantos das peças evitam o número).
COLS = [157, 292, 427, 562]
ROWS = [534, 669, 804, 939]
OFFSET = -45
PALETA = {
    0: (205, 193, 180), 2: (238, 228, 218), 4: (237, 224, 200), 8: (242, 177, 121),
    16: (245, 149, 99), 32: (246, 124, 95), 64: (246, 94, 59), 128: (237, 207, 114),
    256: (237, 204, 97), 512: (237, 200, 80), 1024: (237, 197, 63), 2048: (237, 194, 46),
}
SWIPES = {
    "baixo": (360, 520, 360, 960), "esquerda": (600, 750, 120, 750),
    "direita": (120, 750, 600, 750), "cima": (360, 960, 360, 520),
}


def ler_tabuleiro(tela) -> list[list[int]]:
    if (tela.largura, tela.altura) != (720, 1280):
        raise PrecisaLLM(f"resolução {tela.largura}x{tela.altura} diferente da esperada (720x1280)")
    tab = []
    for y in ROWS:
        linha = []
        for x in COLS:
            valor, dist = cor_mais_proxima(tela.pixel(x + OFFSET, y + OFFSET), PALETA)
            if dist > 30:
                raise PrecisaLLM(f"cor desconhecida em ({x},{y}): {tela.pixel(x + OFFSET, y + OFFSET)} — o jogo está aberto?")
            linha.append(valor)
        tab.append(linha)
    return tab


def _junta(linha):
    """Desliza uma linha para a esquerda; devolve (linha nova, pontos)."""
    nums = [v for v in linha if v]
    out, pontos, i = [], 0, 0
    while i < len(nums):
        if i + 1 < len(nums) and nums[i] == nums[i + 1]:
            out.append(nums[i] * 2)
            pontos += nums[i] * 2
            i += 2
        else:
            out.append(nums[i])
            i += 1
    return out + [0] * (4 - len(out)), pontos


def simular(tab, jogada):
    t = [list(r) for r in tab]
    if jogada in ("cima", "baixo"):
        t = [list(c) for c in zip(*t)]
    if jogada in ("direita", "baixo"):
        t = [r[::-1] for r in t]
    pontos = 0
    for i, r in enumerate(t):
        t[i], p = _junta(r)
        pontos += p
    if jogada in ("direita", "baixo"):
        t = [r[::-1] for r in t]
    if jogada in ("cima", "baixo"):
        t = [list(c) for c in zip(*t)]
    return t, pontos


def descrever(tab, jogada):
    novo, pontos = simular(tab, jogada)
    vazias = sum(v == 0 for r in novo for v in r)
    maior = max(max(r) for r in novo)
    canto = novo[3][0] == maior
    return {
        "pontos_ganhos": pontos,
        "casas_vazias_depois": vazias,
        "maior_peca": maior,
        "maior_no_canto_inferior_esquerdo": canto,
        "tabuleiro_depois": novo,
    }


def regra_local(legais: dict) -> dict:
    """Plano B sem Jev: mais casas vazias e pontos, maior peça no canto, evitar 'cima'."""
    pref = {"baixo": 3, "esquerda": 2, "direita": 1, "cima": -5}
    nota = {j: f["casas_vazias_depois"] * 10 + f["pontos_ganhos"] / 4
            + (8 if f["maior_no_canto_inferior_esquerdo"] else 0) + pref[j] for j, f in legais.items()}
    return {"choice": max(nota, key=nota.get), "confidence": 1.0}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sem_jev = "--sem-jev" in sys.argv
    jogadas = int(args[0]) if args else 30
    cel = Celular()
    cel.abrir("com.uberspot.a2048")
    tela = cel.tela()
    tab = ler_tabuleiro(tela)
    placar, inicio = 0, time.time()
    for n in range(1, jogadas + 1):
        legais = {j: descrever(tab, j) for j in SWIPES if simular(tab, j)[0] != tab}
        if not legais:
            print(f"FIM DE JOGO na jogada {n}. Placar ~{placar}, maior peça {max(max(r) for r in tab)}")
            return
        t0 = time.time()
        resp = regra_local(legais) if sem_jev else jev(
            {"jogo": "2048", "tabuleiro_de_cima_para_baixo": tab, "opcoes": legais},
            {"jogada": escolha(
                "Escolha a melhor jogada de 2048. Estratégia: manter a maior peça no canto inferior esquerdo, "
                "preferir 'baixo' e 'esquerda', maximizar casas vazias e junções; evitar 'cima'.",
                list(legais),
            )},
        )["jogada"]
        decisao_ms = (time.time() - t0) * 1000
        jogada = resp["choice"]
        cel.deslizar(*SWIPES[jogada])
        time.sleep(0.25)
        cel.esperar_mudar(tela.hash)
        time.sleep(0.2)  # fim da animação
        tela = cel.tela()
        novo_tab = ler_tabuleiro(tela)
        if novo_tab == tab:
            raise PrecisaLLM(f"a jogada '{jogada}' não mudou o tabuleiro (gesto não registrado?)")
        placar += legais[jogada]["pontos_ganhos"]
        tab = novo_tab
        print(f"jogada {n:2d}: {jogada:8s} {'regra' if sem_jev else 'jev'} {resp['confidence']:.2f} em {decisao_ms:4.0f} ms | "
              f"placar ~{placar} | maior {max(max(r) for r in tab)}", flush=True)
    print(f"OK: {jogadas} jogadas em {time.time() - inicio:.0f}s. Placar ~{placar}, maior peça {max(max(r) for r in tab)}")
    cel.salvar_print()


if __name__ == "__main__":
    rodar(main)
