import pytest

from kungfu_chess.model.board import Board, DuplicateOccupancyError
from kungfu_chess.model.piece import Piece
from kungfu_chess.model.position import Position


def make_piece(id_, color, kind, row, col):
    return Piece(id=id_, color=color, kind=kind, cell=Position(row, col))


def test_dimensions_inferred():
    b = Board(width=3, height=2)
    assert b.width == 3
    assert b.height == 2


def test_empty_cell_returns_none():
    b = Board(3, 3)
    assert b.piece_at(Position(0, 0)) is None
    assert b.is_empty(Position(0, 0))


def test_occupied_cell_returns_piece():
    b = Board(3, 3)
    p = make_piece(1, 'w', 'K', 0, 0)
    b.add_piece(p)
    assert b.piece_at(Position(0, 0)) is p
    assert not b.is_empty(Position(0, 0))


def test_duplicate_cell_occupancy_rejected():
    b = Board(3, 3)
    b.add_piece(make_piece(1, 'w', 'K', 0, 0))
    with pytest.raises(DuplicateOccupancyError):
        b.add_piece(make_piece(2, 'b', 'K', 0, 0))


def test_move_piece_updates_source_and_destination():
    b = Board(3, 3)
    b.add_piece(make_piece(1, 'w', 'R', 0, 0))
    b.move_piece(Position(0, 0), Position(0, 2))
    assert b.is_empty(Position(0, 0))
    assert b.piece_at(Position(0, 2)).id == 1


def test_remove_piece_clears_cell():
    b = Board(3, 3)
    b.add_piece(make_piece(1, 'w', 'R', 0, 0))
    removed = b.remove_piece(Position(0, 0))
    assert removed.id == 1
    assert b.is_empty(Position(0, 0))


def test_piece_by_id_lookup():
    b = Board(3, 3)
    b.add_piece(make_piece(7, 'w', 'Q', 1, 1))
    assert b.piece_by_id(7).cell == Position(1, 1)
