from kungfu_chess.model.board import Board
from kungfu_chess.model.piece import Piece, PieceState
from kungfu_chess.model.position import Position
from kungfu_chess.realtime.real_time_arbiter import RealTimeArbiter


def make_piece(id_, color, kind, row, col):
    return Piece(id=id_, color=color, kind=kind, cell=Position(row, col))


def test_one_square_move_not_arrived_before_1000ms():
    b = Board(4, 4)
    p = make_piece(1, 'w', 'R', 0, 0)
    b.add_piece(p)
    arb = RealTimeArbiter()
    arb.start_motion(p, Position(0, 1), now_ms=0)
    events = arb.advance_time(b, 999)
    assert events == []
    assert b.piece_at(Position(0, 0)) is p  # still on source cell


def test_one_square_move_arrives_at_1000ms():
    b = Board(4, 4)
    p = make_piece(1, 'w', 'R', 0, 0)
    b.add_piece(p)
    arb = RealTimeArbiter()
    arb.start_motion(p, Position(0, 1), now_ms=0)
    events = arb.advance_time(b, 1000)
    assert len(events) == 1
    assert b.piece_at(Position(0, 1)) is p
    assert p.state == PieceState.IDLE


def test_multi_square_move_scales_with_distance():
    b = Board(4, 4)
    p = make_piece(1, 'w', 'R', 0, 0)
    b.add_piece(p)
    arb = RealTimeArbiter()
    arb.start_motion(p, Position(0, 3), now_ms=0)
    assert arb.advance_time(b, 2999) == []
    events = arb.advance_time(b, 3000)
    assert len(events) == 1


def test_partial_then_remaining_wait_equals_full_wait():
    b = Board(4, 4)
    p = make_piece(1, 'w', 'R', 0, 0)
    b.add_piece(p)
    arb = RealTimeArbiter()
    arb.start_motion(p, Position(0, 2), now_ms=0)
    arb.advance_time(b, 1000)   # partial
    events = arb.advance_time(b, 2000)  # remaining
    assert len(events) == 1
    assert b.piece_at(Position(0, 2)) is p


# ---- Iteration 10: simultaneous movement ------------------------------

def test_two_different_pieces_can_move_at_the_same_time():
    b = Board(4, 4)
    p1 = make_piece(1, 'w', 'R', 0, 0)
    p2 = make_piece(2, 'b', 'R', 3, 3)
    b.add_piece(p1)
    b.add_piece(p2)
    arb = RealTimeArbiter(max_concurrent_motions=None)  # extra route: unlimited

    assert arb.can_start_motion(1) is True
    arb.start_motion(p1, Position(0, 1), now_ms=0)
    assert arb.can_start_motion(2) is True  # a DIFFERENT piece may still start
    arb.start_motion(p2, Position(3, 2), now_ms=0)

    events = arb.advance_time(b, 1000)
    assert len(events) == 2
    assert b.piece_at(Position(0, 1)) is p1
    assert b.piece_at(Position(3, 2)) is p2


def test_same_piece_cannot_start_a_second_motion_while_moving():
    b = Board(4, 4)
    p = make_piece(1, 'w', 'R', 0, 0)
    b.add_piece(p)
    arb = RealTimeArbiter(max_concurrent_motions=None)
    arb.start_motion(p, Position(0, 3), now_ms=0)
    assert arb.can_start_motion(1) is False


def test_max_concurrent_motions_one_reproduces_common_route():
    b = Board(4, 4)
    p1 = make_piece(1, 'w', 'R', 0, 0)
    p2 = make_piece(2, 'b', 'R', 3, 3)
    b.add_piece(p1)
    b.add_piece(p2)
    arb = RealTimeArbiter(max_concurrent_motions=1)  # common route
    arb.start_motion(p1, Position(0, 1), now_ms=0)
    assert arb.can_start_motion(2) is False  # blocked globally, like before
