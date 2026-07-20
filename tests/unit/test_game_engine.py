from kungfu_chess.model.board import Board
from kungfu_chess.model.piece import Piece
from kungfu_chess.model.position import Position
from kungfu_chess.model.game_state import GameState
from kungfu_chess.engine.game_engine import GameEngine
import kungfu_chess.config as config


def make_piece(id_, color, kind, row, col):
    return Piece(id=id_, color=color, kind=kind, cell=Position(row, col))


def build_engine(*pieces, max_concurrent=None):
    from kungfu_chess.realtime.real_time_arbiter import RealTimeArbiter
    b = Board(4, 4)
    for p in pieces:
        b.add_piece(p)
    return GameEngine(b, arbiter=RealTimeArbiter(max_concurrent_motions=max_concurrent))


def test_game_over_checked_before_rule_engine():
    engine = build_engine(make_piece(1, 'w', 'R', 0, 0))
    engine._state.game_over = True
    result = engine.request_move(Position(0, 0), Position(0, 1))
    assert result.is_accepted is False
    assert result.reason == "game_over"


def test_legal_move_delegated_to_rule_engine():
    engine = build_engine(make_piece(1, 'w', 'R', 0, 0))
    result = engine.request_move(Position(0, 0), Position(0, 3))
    assert result.is_accepted is True
    assert result.reason == "ok"


def test_illegal_move_reason_comes_from_rule_engine():
    engine = build_engine(make_piece(1, 'w', 'R', 0, 0))
    result = engine.request_move(Position(0, 0), Position(1, 1))
    assert result.is_accepted is False
    assert result.reason == "illegal_piece_move"


def test_invalid_command_does_not_mutate_board():
    engine = build_engine(make_piece(1, 'w', 'R', 0, 0))
    engine.request_move(Position(0, 0), Position(1, 1))
    assert engine.board.piece_at(Position(0, 0)) is not None


def test_common_route_rejects_second_move_while_any_motion_active():
    engine = build_engine(
        make_piece(1, 'w', 'R', 0, 0),
        make_piece(2, 'b', 'R', 3, 3),
        max_concurrent=1,
    )
    engine.request_move(Position(0, 0), Position(0, 1))
    result = engine.request_move(Position(3, 3), Position(3, 2))
    assert result.is_accepted is False
    assert result.reason == "motion_in_progress"


def test_extra_route_allows_two_different_pieces_moving_at_once():
    engine = build_engine(
        make_piece(1, 'w', 'R', 0, 0),
        make_piece(2, 'b', 'R', 3, 3),
        max_concurrent=None,
    )
    engine.request_move(Position(0, 0), Position(0, 1))
    result = engine.request_move(Position(3, 3), Position(3, 2))
    assert result.is_accepted is True


def test_same_piece_still_cannot_move_twice_even_in_extra_route():
    engine = build_engine(make_piece(1, 'w', 'R', 0, 0), max_concurrent=None)
    engine.request_move(Position(0, 0), Position(0, 1))
    result = engine.request_move(Position(0, 0), Position(0, 2))
    assert result.is_accepted is False
    assert result.reason == "motion_in_progress"


def test_king_capture_sets_game_over():
    engine = build_engine(
        make_piece(1, 'w', 'R', 0, 0),
        make_piece(2, 'b', 'K', 0, 3),
    )
    engine.request_move(Position(0, 0), Position(0, 3))
    engine.wait(3000)  # 3 squares -> 3000ms
    snap = engine.snapshot()
    assert snap.game_over is True
    assert snap.winner == 'w'


def test_command_after_game_over_is_rejected_and_board_unchanged():
    engine = build_engine(
        make_piece(1, 'w', 'R', 0, 0),
        make_piece(2, 'b', 'K', 0, 3),
        make_piece(3, 'w', 'N', 2, 2),
    )
    engine.request_move(Position(0, 0), Position(0, 3))
    engine.wait(3000)  # king captured, game over
    result = engine.request_move(Position(2, 2), Position(0, 1))
    assert result.is_accepted is False
    assert result.reason == "game_over"


def test_captures_is_empty_before_any_capture_happens():
    engine = build_engine(make_piece(1, 'w', 'R', 0, 0))
    assert engine.snapshot().captures == []


def test_a_non_king_capture_is_recorded_with_its_kind_and_color():
    engine = build_engine(
        make_piece(1, 'w', 'R', 0, 0),
        make_piece(2, 'b', 'P', 0, 3),
    )
    engine.request_move(Position(0, 0), Position(0, 3))
    engine.wait(3000)

    assert engine.snapshot().captures == [('P', 'b')]


def test_a_king_capture_is_recorded_in_captures_too_not_just_game_over():
    engine = build_engine(
        make_piece(1, 'w', 'R', 0, 0),
        make_piece(2, 'b', 'K', 0, 3),
    )
    engine.request_move(Position(0, 0), Position(0, 3))
    engine.wait(3000)

    assert engine.snapshot().captures == [('K', 'b')]


def test_captures_accumulate_across_multiple_arrivals():
    engine = build_engine(
        make_piece(1, 'w', 'R', 0, 0),
        make_piece(2, 'b', 'P', 0, 3),
        make_piece(3, 'w', 'N', 3, 0),
        make_piece(4, 'b', 'P', 2, 2),  # a legal knight-move away from (3,0)
    )
    engine.request_move(Position(0, 0), Position(0, 3))  # rook captures pawn
    engine.request_move(Position(3, 0), Position(2, 2))  # knight captures pawn
    engine.wait(5000)

    assert engine.snapshot().captures == [('P', 'b'), ('P', 'b')]


def test_snapshot_captures_is_a_copy_not_a_live_reference():
    engine = build_engine(
        make_piece(1, 'w', 'R', 0, 0),
        make_piece(2, 'b', 'P', 0, 3),
    )
    engine.request_move(Position(0, 0), Position(0, 3))
    engine.wait(3000)

    snapshot_captures = engine.snapshot().captures
    snapshot_captures.append(('Q', 'w'))  # mutate the returned list

    assert engine.snapshot().captures == [('P', 'b')]  # internal state untouched


# ---- completed_moves / algebraic notation ------------------------------

def build_engine_8x8(*pieces, max_concurrent=None):
    from kungfu_chess.realtime.real_time_arbiter import RealTimeArbiter
    b = Board(8, 8)
    for p in pieces:
        b.add_piece(p)
    return GameEngine(b, arbiter=RealTimeArbiter(max_concurrent_motions=max_concurrent))


def test_completed_moves_empty_before_any_move():
    engine = build_engine_8x8(make_piece(1, 'w', 'P', 6, 4))
    assert engine.snapshot().completed_moves == []


def test_simple_pawn_move_recorded_as_plain_square():
    engine = build_engine_8x8(make_piece(1, 'w', 'P', 6, 4))
    engine.request_move(Position(6, 4), Position(4, 4))  # e2-e4, double step
    engine.wait(2000)  # 2 squares -> 2000ms
    assert engine.snapshot().completed_moves == [('w', 'e4', 2000)]


def test_capture_move_recorded_with_piece_letter_and_x():
    engine = build_engine_8x8(
        make_piece(1, 'w', 'R', 7, 0),
        make_piece(2, 'b', 'P', 7, 3),
    )
    engine.request_move(Position(7, 0), Position(7, 3))
    engine.wait(3000)
    assert engine.snapshot().completed_moves == [('w', 'Rxd1', 3000)]


def test_pawn_capture_uses_source_file_prefix_not_piece_letter():
    engine = build_engine_8x8(
        make_piece(1, 'w', 'P', 6, 4),
        make_piece(2, 'b', 'P', 5, 5),
    )
    engine.request_move(Position(6, 4), Position(5, 5))
    engine.wait(1000)
    assert engine.snapshot().completed_moves == [('w', 'exf3', 1000)]


def test_promotion_recorded_with_equals_suffix_and_no_piece_letter():
    engine = build_engine_8x8(make_piece(1, 'w', 'P', 1, 0))
    engine.request_move(Position(1, 0), Position(0, 0))
    engine.wait(1000)
    assert engine.snapshot().completed_moves == [('w', 'a8=Q', 1000)]


def test_disambiguation_when_two_knights_can_reach_same_square():
    engine = build_engine_8x8(
        make_piece(1, 'w', 'N', 4, 2),  # c4
        make_piece(2, 'w', 'N', 3, 1),  # b5, also reaches d6
    )
    engine.request_move(Position(4, 2), Position(2, 3))  # Nc4-d6
    engine.wait(2000)  # steps = max(2,1) = 2 -> 2000ms
    assert engine.snapshot().completed_moves == [('w', 'Ncd6', 2000)]


def test_no_disambiguation_when_only_one_piece_of_that_kind_can_reach_it():
    engine = build_engine_8x8(make_piece(1, 'w', 'N', 4, 2))
    engine.request_move(Position(4, 2), Position(2, 3))
    engine.wait(2000)
    assert engine.snapshot().completed_moves == [('w', 'Nd6', 2000)]


def test_jump_does_not_appear_in_completed_moves():
    engine = build_engine_8x8(make_piece(1, 'w', 'R', 7, 0))
    engine.request_jump(Position(7, 0))
    engine.wait(config.JUMP_DURATION_MS)
    assert engine.snapshot().completed_moves == []


def test_completed_moves_from_both_colors_stay_in_completion_order():
    engine = build_engine_8x8(
        make_piece(1, 'w', 'P', 6, 4),
        make_piece(2, 'b', 'P', 1, 3),
    )
    engine.request_move(Position(6, 4), Position(5, 4))  # e2-e3, white, 1 square
    engine.request_move(Position(1, 3), Position(3, 3))  # d7-d5, black, 2 squares
    engine.wait(1000)
    assert engine.snapshot().completed_moves == [('w', 'e3', 1000)]

    engine.wait(1000)
    assert engine.snapshot().completed_moves == [('w', 'e3', 1000), ('b', 'd5', 2000)]


def test_snapshot_completed_moves_is_a_copy_not_a_live_reference():
    engine = build_engine_8x8(make_piece(1, 'w', 'P', 6, 4))
    engine.request_move(Position(6, 4), Position(5, 4))
    engine.wait(1000)

    snapshot_moves = engine.snapshot().completed_moves
    snapshot_moves.append(('b', 'zzz', 999))

    assert engine.snapshot().completed_moves == [('w', 'e3', 1000)]
