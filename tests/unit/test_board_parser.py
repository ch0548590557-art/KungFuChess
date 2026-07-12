import pytest

from kungfu_chess.io.board_parser import BoardParser, BoardParseError
from kungfu_chess.model.position import Position


def test_accepts_rectangular_board():
    rows = [["wK", ".", "."], [".", "wR", "."]]
    board = BoardParser().parse(rows)
    assert board.width == 3
    assert board.height == 2
    assert board.piece_at(Position(0, 0)).kind == 'K'


def test_rejects_inconsistent_row_length():
    rows = [["wK", "."], ["."]]
    with pytest.raises(BoardParseError) as exc:
        BoardParser().parse(rows)
    assert exc.value.reason == "row_width_mismatch"


def test_rejects_illegal_piece_token():
    rows = [["wZ", "."]]
    with pytest.raises(BoardParseError) as exc:
        BoardParser().parse(rows)
    assert exc.value.reason == "unknown_token"


def test_piece_ids_assigned_deterministically_in_reading_order():
    rows = [["wK", "bR"]]
    board = BoardParser().parse(rows)
    assert board.piece_at(Position(0, 0)).id == 1
    assert board.piece_at(Position(0, 1)).id == 2
