from kungfu_chess.model.board import Board
from kungfu_chess.model.piece import Piece
from kungfu_chess.model.position import Position
from kungfu_chess.rules.rule_engine import RuleEngine


def make_piece(id_, color, kind, row, col):
    return Piece(id=id_, color=color, kind=kind, cell=Position(row, col))


def test_outside_board_rejected():
    b = Board(4, 4)
    b.add_piece(make_piece(1, 'w', 'R', 0, 0))
    result = RuleEngine().validate_move(b, Position(0, 0), Position(9, 9))
    assert result.is_valid is False
    assert result.reason == "outside_board"


def test_empty_source_rejected():
    b = Board(4, 4)
    result = RuleEngine().validate_move(b, Position(0, 0), Position(1, 1))
    assert result.is_valid is False
    assert result.reason == "empty_source"


def test_friendly_destination_rejected():
    b = Board(4, 4)
    b.add_piece(make_piece(1, 'w', 'R', 0, 0))
    b.add_piece(make_piece(2, 'w', 'P', 0, 2))
    result = RuleEngine().validate_move(b, Position(0, 0), Position(0, 2))
    assert result.is_valid is False
    assert result.reason == "friendly_destination"


def test_illegal_piece_move_rejected():
    b = Board(4, 4)
    b.add_piece(make_piece(1, 'w', 'R', 0, 0))
    result = RuleEngine().validate_move(b, Position(0, 0), Position(1, 1))
    assert result.is_valid is False
    assert result.reason == "illegal_piece_move"


def test_legal_move_accepted():
    b = Board(4, 4)
    b.add_piece(make_piece(1, 'w', 'R', 0, 0))
    result = RuleEngine().validate_move(b, Position(0, 0), Position(0, 3))
    assert result.is_valid is True
    assert result.reason == "ok"
