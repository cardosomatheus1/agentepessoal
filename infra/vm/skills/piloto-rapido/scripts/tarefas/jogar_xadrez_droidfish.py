#!/opt/venv/bin/python
"""Play ONE existing DroidFish game as White through screen pixels and ADB.

Never installs, starts a new game, accepts terms or logs in. Resume is the default.
The UI must already show Play White, standard pieces and White at the bottom.
Evidence/checkpoints default to /a0/usr/workdir/chess_evidence.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from piloto import Celular, PrecisaLLM, escolha, jev
from chess_inference import occupancy, infer_moves
import chess
import chess.engine
import chess.pgn

PACKAGE = 'org.petero.droidfish'


def read_occupancy(screen, bounds):
    """Sample 8x8 grid. Exact sprite colors ignore blue/green hint arrows.

    Standard DroidFish sprites: dark ink RGB 40, white fill RGB 240.
    Calibrated at 720x1280, 90px cells; fail closed on changed theme/scale.
    """
    x1, y1, x2, y2 = bounds
    if (x2-x1, y2-y1) != (720, 720):
        raise PrecisaLLM('Calibration requires a 720x720 chessboard')
    cells = [0]*64
    for row in range(8):
        for col in range(8):
            dark = light = 0
            for y in range(y1+row*90+15, y1+row*90+76, 2):
                for x in range(x1+col*90+15, x1+col*90+76, 2):
                    p = screen.pixel(x,y)
                    dark += p == (40,40,40)
                    light += p == (240,240,240)
            cells[chess.square(col,7-row)] = (1 if light >= 90 else 2) if dark >= 40 else 0
    return tuple(cells)


VALOR = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def _material(board, color):
    return sum(VALOR[p.piece_type] for p in board.piece_map().values() if p.color == color)


def _risco(board, move):
    """Depois do lance: maior valor que o adversário ganha com uma captura imediata (já descontando a recaptura simples)."""
    after = board.copy(); after.push(move)
    pior = 0
    for r in after.legal_moves:
        if not after.is_capture(r):
            continue
        alvo = after.piece_at(r.to_square)
        ganho = VALOR[alvo.piece_type] if alvo else 1  # en passant
        a2 = after.copy(); a2.push(r)
        if any(a2.is_capture(x) and x.to_square == r.to_square for x in a2.legal_moves):
            ganho -= VALOR[a2.piece_at(r.to_square).piece_type]
        pior = max(pior, ganho)
    return pior


def candidatos_jev(board, limite=10):
    """Código mede cada lance legal; devolve os melhores candidatos com a descrição para o Jev."""
    lista = []
    for m in board.legal_moves:
        san = board.san(m)
        alvo = board.piece_at(m.to_square)
        captura = VALOR[alvo.piece_type] if alvo else (1 if board.is_en_passant(m) else 0)
        after = board.copy(); after.push(m)
        mate = after.is_checkmate()
        risco = 0 if mate else _risco(board, m)
        saldo = captura - risco
        nota = (1000 if mate else 0) + saldo * 10 + (2 if board.gives_check(m) else 0) + (3 if board.is_castling(m) else 0)
        if len(board.move_stack) < 16 and board.piece_at(m.from_square).piece_type in (chess.KNIGHT, chess.BISHOP) \
                and chess.square_rank(m.from_square) in (0, 7):
            nota += 2  # desenvolver peças na abertura
        partes = []
        if mate: partes.append("XEQUE-MATE")
        if captura: partes.append(f"captura {captura} ponto(s)")
        if board.gives_check(m) and not mate: partes.append("dá xeque")
        if board.is_castling(m): partes.append("roque")
        partes.append(f"pode perder {risco} ponto(s) na resposta" if risco > 0 else "não deixa peça solta")
        partes.append(f"saldo de material {saldo:+d}")
        lista.append((nota, san, "; ".join(partes), m))
    lista.sort(key=lambda t: t[0], reverse=True)
    return lista[:limite]


def center(square, bounds):
    return (bounds[0]+90*chess.square_file(square)+45,
            bounds[1]+90*(7-chess.square_rank(square))+45)


def ui_status(cel):
    elements = cel.elementos()
    status = next((e['texto'] for e in elements if e['id'].endswith('/status')), '')
    title = next((e['texto'] for e in elements if e['id'].endswith('/title_text')), '')
    return status, title, elements


def save_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2)+'\n')
    temporary.replace(path)


def restore_board(state):
    board = chess.Board()
    for uci in state.get('moves', []):
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise PrecisaLLM('Checkpoint contains an illegal move')
        board.push(move)
    if state.get('fen', board.fen()) != board.fen():
        raise PrecisaLLM('Checkpoint FEN does not agree with move history')
    return board


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', default='/a0/usr/workdir/chess_evidence')
    parser.add_argument('--engine', default='/usr/games/stockfish')
    parser.add_argument('--think', type=float, default=.25)
    parser.add_argument('--computer-seconds', type=float, default=2.0,
                        help='Request app stopSearch after this wait; 0 disables')
    parser.add_argument('--max-plies', type=int, default=400,
                        help='Safety pause, never declared a finished game')
    parser.add_argument('--pause-after', type=int, default=0,
                        help='Pause after N new verified plies for a smoke test')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--decisor', choices=['stockfish', 'jev'], default='stockfish',
                        help='Quem escolhe os lances das brancas: motor local ou Jev (TypeSafe)')
    args = parser.parse_args()
    if args.think <= 0 or args.computer_seconds < 0:
        parser.error('Invalid engine time')
    folder = Path(args.evidence)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder/'state.json'
    cel = Celular('android:5555')
    status, title, elements = ui_status(cel)
    boards = [e for e in elements if e['id'].endswith('/chessboard')]
    if len(boards) != 1:
        raise PrecisaLLM('DroidFish chessboard is not visible')
    bounds = boards[0]['bounds']
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text())
        if tuple(state['bounds']) != tuple(bounds):
            raise PrecisaLLM('Board geometry changed since checkpoint')
    else:
        state = {'package': PACKAGE, 'color': 'white', 'difficulty': title,
                 'bounds': bounds, 'moves': [], 'fen': chess.STARTING_FEN,
                 'pending': None, 'completed': False, 'force_requests': 0,
                 'started_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                 'computer_seconds': args.computer_seconds}
        if not title.startswith('Stockfish: 1320'):
            raise PrecisaLLM('Expected preconfigured Stockfish: 1320')
    board = restore_board(state)
    observed = read_occupancy(cel.tela(), bounds)
    if args.check_only:
        if observed != occupancy(board):
            raise PrecisaLLM('Screen occupancy differs from checkpoint/initial position')
        print('CHECK_OK: 64 cells match legal board; '+title, flush=True)
        return
    if state['completed']:
        print('ALREADY_COMPLETED: refusing to play a second game', flush=True)
        return
    if not state['moves'] and not state['pending'] and observed != occupancy(board):
        raise PrecisaLLM('No checkpoint and screen is not initial position')
    save_json(checkpoint,state)
    start_plies = len(board.move_stack)
    wait_since = time.monotonic()
    forced = False
    pending_since = time.monotonic()

    def persist():
        state['fen'] = board.fen()
        state['moves'] = [m.uci() for m in board.move_stack]
        save_json(checkpoint,state)

    def confirm(move, who):
        san = board.san(move)
        board.push(move)
        persist()
        print(f'PLY {len(board.move_stack):03d} {who}: {san} ({move.uci()})', flush=True)

    def finish():
        result = board.result(claim_draw=False)
        st, ttl, es = ui_status(cel)
        # Do not fabricate terminal UI proof: record actual app text and position.
        path = str(folder/'final.png')
        cel.salvar_print(path)
        xml = cel._adb('exec-out','cat','/sdcard/ui.xml')
        (folder/'final-ui.xml').write_text(xml)
        if read_occupancy(cel.tela(), bounds) != occupancy(board):
            raise PrecisaLLM('Terminal screen no longer matches final board')
        term = board.outcome(claim_draw=False)
        state.update(completed=True, pending=None, result=result,
                     termination=term.termination.name if term else 'UNKNOWN',
                     plies=len(board.move_stack), white_moves=(len(board.move_stack)+1)//2,
                     black_moves=len(board.move_stack)//2, status=st, title=ttl,
                     finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'), screenshot=path)
        persist()
        game=chess.pgn.Game.from_board(board)
        game.headers.update(Event='One real Android computer game', Site='DroidFish Android',
                            White=('ADB automation / Jev (TypeSafe)' if args.decisor == 'jev' else 'ADB automation / Stockfish 17'),
                            Black='DroidFish Stockfish 1320',
                            Result=result, Date=time.strftime('%Y.%m.%d'))
        (folder/'game.pgn').write_text(str(game)+'\n')
        save_json(folder/'result.json',state)
        print('COMPLETED '+json.dumps({k:state[k] for k in
              ('result','termination','plies','white_moves','black_moves','status','screenshot','force_requests')}),flush=True)

    import contextlib
    engine_ctx = chess.engine.SimpleEngine.popen_uci(args.engine) if args.decisor == 'stockfish' else contextlib.nullcontext()
    with engine_ctx as engine:
        if engine:
            engine.configure({'Threads':1,'Hash':32})
        while len(board.move_stack) < args.max_plies:
            observed = read_occupancy(cel.tela(),bounds)
            if state['pending']:
                move = chess.Move.from_uci(state['pending'])
                after=board.copy(); after.push(move)
                replies=infer_moves(after,observed)
                if observed == occupancy(after) or len(replies) == 1:
                    state['pending']=None
                    confirm(move,'WHITE')
                    wait_since=time.monotonic(); forced=False
                    if replies and observed != occupancy(after):
                        confirm(replies[0],'COMPUTER')
                    continue
                if time.monotonic()-pending_since > 20:
                    cel.salvar_print(str(folder/'needs_attention.png'))
                    raise PrecisaLLM('White move not confirmed; pending retained, no automatic retry')
                time.sleep(.12)
                continue
            if observed != occupancy(board):
                if board.turn != chess.WHITE:
                    moves=infer_moves(board,observed)
                    if len(moves)==1:
                        confirm(moves[0],'COMPUTER')
                        continue
                    if len(moves)>1:
                        # Occupancy alone cannot determine promotion piece type.
                        cel.salvar_print(str(folder/'needs_attention.png'))
                        raise PrecisaLLM('Ambiguous computer promotion: '+str(moves))
                if time.monotonic()-wait_since > 30:
                    cel.salvar_print(str(folder/'needs_attention.png'))
                    raise PrecisaLLM('Unexpected screen occupancy; stop without altering game')
                time.sleep(.15)
                continue
            if board.is_game_over(claim_draw=False):
                finish()
                return
            if args.pause_after and len(board.move_stack)-start_plies >= args.pause_after and board.turn==chess.WHITE:
                cel.salvar_print(str(folder/'paused.png'))
                print('PAUSED verified checkpoint at ply '+str(len(board.move_stack)),flush=True)
                return
            if board.turn==chess.WHITE:
                if args.decisor == 'jev':
                    cands = candidatos_jev(board)
                    opcoes = {san: desc for _, san, desc, _ in cands}
                    t0 = time.monotonic()
                    r = jev({"jogo": "xadrez", "minha_cor": "brancas", "posicao_fen": board.fen(),
                             "ultimos_lances": [m.uci() for m in board.move_stack[-6:]],
                             "material": {"meu": _material(board, chess.WHITE), "adversario": _material(board, chess.BLACK)}},
                            {"lance": escolha("Escolha o melhor lance de xadrez para as brancas. Priorize xeque-mate, "
                                              "ganhar material sem perder peças, segurança do rei e desenvolvimento.", opcoes)})["lance"]
                    chosen = next(m for _, san, _, m in cands if san == r["choice"])
                    print(f"JEV escolheu {r['choice']} (confiança {r['confidence']:.2f}, {1000*(time.monotonic()-t0):.0f} ms) "
                          f"entre {len(cands)} candidatos", flush=True)
                else:
                    chosen=engine.play(board,chess.engine.Limit(time=args.think)).move
                if chosen not in board.legal_moves:
                    raise PrecisaLLM('Local engine returned illegal move')
                if chosen.promotion and chosen.promotion != chess.QUEEN:
                    raise PrecisaLLM('Underpromotion requires UI adaptation; no action performed')
                state['pending']=chosen.uci(); persist()
                pending_since=time.monotonic()
                cel.tocar(*center(chosen.from_square,bounds))
                cel.tocar(*center(chosen.to_square,bounds))
                if chosen.promotion:
                    _,_,es=ui_status(cel)
                    queens=[e for e in es if re.search(r'queen|dama',e['texto']+' '+e['descricao'],re.I)]
                    if len(queens)!=1:
                        cel.salvar_print(str(folder/'needs_attention.png'))
                        raise PrecisaLLM('Promotion chooser not recognized; pending retained')
                    cel.tocar(*queens[0]['centro'])
                continue
            elapsed=time.monotonic()-wait_since
            if args.computer_seconds and elapsed >= args.computer_seconds and not forced:
                # DroidChessController.stopSearch() is guarded by !humansTurn().
                # A reply arriving between these taps cannot make a white move.
                cel.tocar(670,71)
                time.sleep(.65)  # wait for drawer opening animation
                cel.tocar(440,203)
                time.sleep(.65)  # wait for drawer closing animation
                forced=True
                state['force_requests']+=1; persist()
                print('REQUEST app stopSearch()',flush=True)
                time.sleep(.2)
            elif elapsed > 90:
                cel.salvar_print(str(folder/'needs_attention.png'))
                raise PrecisaLLM('Computer response timeout')
            else:
                time.sleep(.15)
    cel.salvar_print(str(folder/'paused.png'))
    raise PrecisaLLM('Safety ply limit reached, game unfinished and resumable')


if __name__=='__main__':
    try:
        main()
    except (PrecisaLLM, chess.engine.EngineError, chess.engine.EngineTerminatedError) as exc:
        print('PRECISA_LLM: '+str(exc),flush=True)
        sys.exit(2)
