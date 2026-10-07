# Tarefas guardadas

Scripts que já funcionaram. Rode direto quando o pedido for o mesmo; adapte quando for parecido.

| Script | O que faz | App | Como rodar | Limitações |
|---|---|---|---|---|
| `jogar_2048.py` | Joga 2048: lê o tabuleiro pelas cores, simula as 4 jogadas e o Jev escolhe | `com.uberspot.a2048` | `python3 jogar_2048.py 30` (`--sem-jev` = regra simples) | Na 1ª abertura o app mostra "Change Log": feche com OK |
| `jogar_xadrez_droidfish.py` | Joga xadrez de brancas no DroidFish contra o Stockfish 1320: lê o tabuleiro pelos pixels, descobre o lance do computador pela ocupação das casas (`chess_inference.py`) e salva o estado para retomar. Escrito pelo próprio agente; modo Jev acrescentado depois | `org.petero.droidfish` | `python3 jogar_xadrez_droidfish.py --decisor jev --evidence /a0/usr/workdir/<pasta-nova>` (`--decisor stockfish` = motor local) | Precisa de partida nova com brancas e título 'Stockfish: 1320'; com Jev perdeu em 37 lances (candidatos com só 1 lance de profundidade); com Stockfish venceu em 24 |
