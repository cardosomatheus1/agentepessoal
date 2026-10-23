"""Offline unittest coverage for occupancy-based legal move inference."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chess_inference import infer_moves, occupancy
import chess


def observed_cells(white=(), black=()):
    """Build observations from explicit square names, not the tested API."""
    cells = [0] * 64
    for color, squares in ((1, white), (2, black)):
        for square in squares:
            cells[chess.parse_square(square)] = color
    return tuple(cells)


class ChessInferenceTests(unittest.TestCase):
    def assert_candidates(self, board, observed, expected):
        before_fen = board.fen(en_passant="fen")
        before_stack = list(board.move_stack)
        actual = infer_moves(board, observed)
        self.assertIsInstance(actual, list)
        self.assertTrue(all(isinstance(move, chess.Move) for move in actual))
        self.assertEqual({move.uci() for move in actual}, set(expected))
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(board.fen(en_passant="fen"), before_fen)
        self.assertEqual(board.move_stack, before_stack)

    def test_occupancy_initial_order(self):
        actual = occupancy(chess.Board())
        self.assertIsInstance(actual, tuple)
        self.assertEqual(actual, (1,) * 16 + (0,) * 32 + (2,) * 16)

    def test_occupancy_sparse_and_empty(self):
        board = chess.Board(None)
        self.assertEqual(occupancy(board), (0,) * 64)
        board.set_piece_at(chess.A1, chess.Piece(chess.ROOK, chess.WHITE))
        board.set_piece_at(chess.H8, chess.Piece(chess.KNIGHT, chess.BLACK))
        self.assertEqual(occupancy(board), (1,) + (0,) * 62 + (2,))

    def test_initial_move(self):
        board = chess.Board()
        observed = list((1,) * 16 + (0,) * 32 + (2,) * 16)
        observed[chess.E2] = 0
        observed[chess.E4] = 1
        self.assert_candidates(board, observed, ["e2e4"])

    def test_capture(self):
        board = chess.Board("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1")
        observed = observed_cells(white=("e1", "d5"), black=("e8",))
        self.assert_candidates(board, observed, ["e4d5"])

    def test_en_passant_and_preserved_history(self):
        board = chess.Board()
        for move in ("e2e4", "a7a6", "e4e5", "d7d5"):
            board.push_uci(move)
        observed = list((1,) * 16 + (0,) * 32 + (2,) * 16)
        for square in (chess.E2, chess.A7, chess.D7):
            observed[square] = 0
        observed[chess.A6] = 2
        observed[chess.D6] = 1
        self.assert_candidates(board, observed, ["e5d6"])

    def test_castling_both_sides_both_colors(self):
        cases = (
            ("w", "e1g1", ("a1", "f1", "g1"), ("a8", "e8", "h8")),
            ("w", "e1c1", ("c1", "d1", "h1"), ("a8", "e8", "h8")),
            ("b", "e8g8", ("a1", "e1", "h1"), ("a8", "f8", "g8")),
            ("b", "e8c8", ("a1", "e1", "h1"), ("c8", "d8", "h8")),
        )
        for turn, move, white, black in cases:
            with self.subTest(move=move):
                board = chess.Board(f"r3k2r/8/8/8/8/8/8/R3K2R {turn} KQkq - 0 1")
                self.assert_candidates(board, observed_cells(white, black), [move])

    def test_promotion_four_candidates(self):
        board = chess.Board("7k/P7/8/8/8/8/8/7K w - - 0 1")
        observed = observed_cells(white=("a8", "h1"), black=("h8",))
        self.assert_candidates(board, observed, ["a7a8q", "a7a8r", "a7a8b", "a7a8n"])

    def test_capture_promotion_four_candidates(self):
        board = chess.Board("1r5k/P7/8/8/8/8/8/7K w - - 0 1")
        observed = observed_cells(white=("b8", "h1"), black=("h8",))
        self.assert_candidates(board, observed, ["a7b8q", "a7b8r", "a7b8b", "a7b8n"])

    def test_invalid_impossible_and_unchanged(self):
        board = chess.Board()
        for observed in ((0,) * 64, (1,) * 16 + (0,) * 32 + (2,) * 16):
            with self.subTest(observed=observed):
                self.assert_candidates(board, observed, [])

    def test_invalid_wrong_color(self):
        board = chess.Board()
        observed = list((1,) * 16 + (0,) * 32 + (2,) * 16)
        observed[chess.E2] = 0
        observed[chess.E4] = 2
        self.assert_candidates(board, observed, [])

    def test_invalid_encoding(self):
        for observed in ((), (0,) * 63, (0,) * 65, (3,) + (0,) * 63):
            with self.subTest(observed=observed):
                self.assert_candidates(chess.Board(), observed, [])

    def test_pinned_piece_illegal_move(self):
        board = chess.Board("k3r3/8/8/8/8/8/4R3/4K3 w - - 0 1")
        observed = observed_cells(white=("e1", "d2"), black=("a8", "e8"))
        self.assert_candidates(board, observed, [])

    def test_no_legal_moves(self):
        board = chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")
        self.assertTrue(board.is_checkmate())
        self.assert_candidates(board, observed_cells(("g6", "g7"), ("h8",)), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
