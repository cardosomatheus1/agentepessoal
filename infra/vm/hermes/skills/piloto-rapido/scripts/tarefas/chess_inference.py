"""Infer legal chess moves from square occupancy, without changing the board.

Only presence and color are observed, not piece type. Promotions can therefore
produce multiple candidates. No UI, engine, or device access is performed.
"""

import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vendor"))
import chess


def occupancy(board: chess.Board) -> tuple[int, ...]:
    """Return 64 cells in square order (a1..h8): empty=0, white=1, black=2."""
    cells = [0] * 64
    for square, piece in board.piece_map().items():
        cells[square] = 1 if piece.color == chess.WHITE else 2
    return tuple(cells)


def infer_moves(board: chess.Board, observed: Sequence[int]) -> list[chess.Move]:
    """Return every legal move whose resulting occupancy exactly matches.

    The supplied board and its history are preserved. An impossible observation
    or one with a length/value outside the 64-cell 0/1/2 encoding returns [].
    Candidate order follows python-chess's legal move iteration order.
    """
    target = tuple(observed)
    if len(target) != 64 or any(cell not in (0, 1, 2) for cell in target):
        return []

    simulated = board.copy(stack=False)
    matches = []
    for move in board.legal_moves:
        simulated.push(move)
        try:
            if occupancy(simulated) == target:
                matches.append(move)
        finally:
            simulated.pop()
    return matches
