import pytest

from kungfu_chess.model.position import Position
from kungfu_chess.network import protocol
from kungfu_chess.network.protocol import (
    CaptureInfo,
    CompletedMove,
    Error,
    GameStateUpdate,
    JumpRequest,
    MotionInfo,
    MoveRequest,
    PieceInfo,
)


def test_move_request_round_trip():
    message = MoveRequest(source=Position(6, 4), destination=Position(4, 4))
    assert protocol.decode(protocol.encode(message)) == message


def test_jump_request_round_trip():
    message = JumpRequest(source=Position(6, 4))
    assert protocol.decode(protocol.encode(message)) == message


def test_error_round_trip():
    message = Error(reason="wrong_color")
    assert protocol.decode(protocol.encode(message)) == message


def test_game_state_update_round_trip_with_full_fields():
    message = GameStateUpdate(
        board_width=8,
        board_height=8,
        pieces=[PieceInfo(kind="K", color="w", row=7, col=4, state="IDLE")],
        game_over=True,
        winner="w",
        motions=[MotionInfo(
            source=Position(6, 4), destination=Position(4, 4),
            start_time_ms=1000, arrival_time_ms=1400,
        )],
        captures=[CaptureInfo(kind="P", color="b")],
        completed_moves=[CompletedMove(color="w", san="e4", timestamp_ms=1400)],
        your_color="w",
    )
    assert protocol.decode(protocol.encode(message)) == message


def test_game_state_update_round_trip_with_empty_lists():
    message = GameStateUpdate(
        board_width=8, board_height=8, pieces=[], game_over=False,
    )
    assert protocol.decode(protocol.encode(message)) == message


def test_decode_unknown_type_raises():
    with pytest.raises(ValueError):
        protocol.decode('{"type": "not_a_real_type"}')


class _FakeSnapshot:
    def __init__(self):
        self.board_width = 8
        self.board_height = 8
        self.pieces = [("K", "w", 7, 4, "IDLE")]
        self.game_over = False
        self.winner = None
        self.motions = {(6, 4): (4, 4, 1000, 1400)}
        self.captures = [("P", "b")]
        self.completed_moves = [("w", "e4", 1400)]


def test_game_state_update_from_snapshot_converts_all_fields():
    update = GameStateUpdate.from_snapshot(_FakeSnapshot(), your_color="b")

    assert update.pieces == [PieceInfo(kind="K", color="w", row=7, col=4, state="IDLE")]
    assert update.motions == [MotionInfo(
        source=Position(6, 4), destination=Position(4, 4),
        start_time_ms=1000, arrival_time_ms=1400,
    )]
    assert update.captures == [CaptureInfo(kind="P", color="b")]
    assert update.completed_moves == [CompletedMove(color="w", san="e4", timestamp_ms=1400)]
    assert update.your_color == "b"