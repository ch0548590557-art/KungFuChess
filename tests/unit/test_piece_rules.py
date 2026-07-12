from kungfu_chess.model.board import Board
from kungfu_chess.model.piece import Piece
from kungfu_chess.model.position import Position
from kungfu_chess.rules.piece_rules import legal_destinations


def make_piece(id_, color, kind, row, col):
    return Piece(id=id_, color=color, kind=kind, cell=Position(row, col))


def test_rook_moves_across_empty_row_and_column():
    b = Board(5, 5)
    rook = make_piece(1, 'w', 'R', 2, 2)
    b.add_piece(rook)
    dests = legal_destinations(b, rook)
    assert Position(0, 2) in dests
    assert Position(2, 4) in dests
    assert Position(1, 1) not in dests  # not a rook direction


def test_rook_stops_before_friendly_blocker():
    b = Board(5, 5)
    rook = make_piece(1, 'w', 'R', 2, 2)
    b.add_piece(rook)
    b.add_piece(make_piece(2, 'w', 'P', 2, 4))
    dests = legal_destinations(b, rook)
    assert Position(2, 3) in dests
    assert Position(2, 4) not in dests


def test_rook_captures_enemy_blocker_but_not_beyond():
    b = Board(6, 6)
    rook = make_piece(1, 'w', 'R', 2, 2)
    b.add_piece(rook)
    b.add_piece(make_piece(2, 'b', 'P', 2, 4))
    dests = legal_destinations(b, rook)
    assert Position(2, 4) in dests       # enemy blocker: legal destination
    assert Position(2, 5) not in dests   # nothing beyond the blocker


def test_rook_cannot_move_diagonally():
    b = Board(5, 5)
    rook = make_piece(1, 'w', 'R', 2, 2)
    b.add_piece(rook)
    dests = legal_destinations(b, rook)
    assert Position(3, 3) not in dests


def test_bishop_moves_diagonally_not_straight():
    b = Board(5, 5)
    bishop = make_piece(1, 'w', 'B', 2, 2)
    b.add_piece(bishop)
    dests = legal_destinations(b, bishop)
    assert Position(0, 0) in dests
    assert Position(2, 0) not in dests


def test_queen_combines_rook_and_bishop():
    b = Board(5, 5)
    queen = make_piece(1, 'w', 'Q', 2, 2)
    b.add_piece(queen)
    dests = legal_destinations(b, queen)
    assert Position(2, 0) in dests  # rook-style
    assert Position(0, 0) in dests  # bishop-style


def test_knight_jumps_over_blockers():
    b = Board(5, 5)
    knight = make_piece(1, 'w', 'N', 2, 2)
    b.add_piece(knight)
    b.add_piece(make_piece(2, 'w', 'P', 2, 3))  # sits "in the way"
    dests = legal_destinations(b, knight)
    assert Position(0, 1) in dests


def test_king_moves_one_cell_only():
    b = Board(5, 5)
    king = make_piece(1, 'w', 'K', 2, 2)
    b.add_piece(king)
    dests = legal_destinations(b, king)
    assert Position(1, 2) in dests
    assert Position(0, 2) not in dests


def test_pawn_moves_forward_and_captures_diagonally():
    b = Board(5, 5)
    pawn = make_piece(1, 'w', 'P', 3, 2)
    b.add_piece(pawn)
    b.add_piece(make_piece(2, 'b', 'P', 2, 3))
    dests = legal_destinations(b, pawn)
    assert Position(2, 2) in dests   # forward
    assert Position(2, 3) in dests   # diagonal capture
    assert Position(2, 1) not in dests  # nothing to capture there
