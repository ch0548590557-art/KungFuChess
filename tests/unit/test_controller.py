from kungfu_chess.model.board import Board
from kungfu_chess.model.piece import Piece
from kungfu_chess.model.position import Position
from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import (
    MouseClickEvent,
    MouseJumpEvent,
    MoveRequestedEvent,
    JumpRequestedEvent,
)
from kungfu_chess.input.board_mapper import BoardMapper
from kungfu_chess.input.controller import Controller
from kungfu_chess.engine.game_engine import GameEngine, MoveResult


class FakeGameEngine:
    """A minimal stand-in so Controller tests don't depend on RuleEngine
    or RealTimeArbiter being correct - only on Controller calling the
    right method with the right arguments (Section 16: 'Controller Unit
    tests with a fake GameEngine')."""

    def __init__(self, board):
        self.board = board
        self.calls = []
        self.jump_calls = []

    def request_move(self, source, destination):
        self.calls.append((source, destination))
        return MoveResult(True, "ok")

    def request_jump(self, source):
        self.jump_calls.append(source)
        return MoveResult(True, "ok")


def build(board):
    return BoardMapper(board), board


def test_first_click_on_piece_selects_it():
    board = Board(4, 4)
    board.add_piece(Piece(id=1, color='w', kind='R', cell=Position(0, 0)))
    engine = FakeGameEngine(board)
    controller = Controller(BoardMapper(board), engine)

    result = controller.click(50, 50)
    assert result.outcome == "selected"
    assert engine.calls == []


def test_first_click_on_empty_cell_does_nothing():
    board = Board(4, 4)
    engine = FakeGameEngine(board)
    controller = Controller(BoardMapper(board), engine)

    result = controller.click(50, 50)
    assert result.outcome == "ignored"


def test_outside_click_with_no_selection_is_ignored():
    board = Board(4, 4)
    engine = FakeGameEngine(board)
    controller = Controller(BoardMapper(board), engine)

    result = controller.click(10000, 10000)
    assert result.outcome == "ignored"


def test_outside_click_with_selection_cancels_and_sends_no_command():
    board = Board(4, 4)
    board.add_piece(Piece(id=1, color='w', kind='R', cell=Position(0, 0)))
    engine = FakeGameEngine(board)
    controller = Controller(BoardMapper(board), engine)

    controller.click(50, 50)  # select
    result = controller.click(10000, 10000)  # outside
    assert result.outcome == "cleared"
    assert engine.calls == []


def test_second_in_board_click_sends_move_and_clears_selection():
    board = Board(4, 4)
    board.add_piece(Piece(id=1, color='w', kind='R', cell=Position(0, 0)))
    engine = FakeGameEngine(board)
    controller = Controller(BoardMapper(board), engine)

    controller.click(50, 50)          # select (0,0)
    result = controller.click(350, 50)  # second click -> (0,3)

    assert result.outcome == "move_requested"
    assert engine.calls == [(Position(0, 0), Position(0, 3))]
    assert controller._selected is None


# ---- EventBus integration -----------------------------------------------

def test_without_bus_click_behaves_exactly_as_before():
    board = Board(4, 4)
    board.add_piece(Piece(id=1, color='w', kind='R', cell=Position(0, 0)))
    engine = FakeGameEngine(board)
    controller = Controller(BoardMapper(board), engine)

    result = controller.click(50, 50)
    assert result.outcome == "selected"


def test_mouse_click_event_triggers_the_same_click_logic():
    board = Board(4, 4)
    board.add_piece(Piece(id=1, color='w', kind='R', cell=Position(0, 0)))
    engine = FakeGameEngine(board)
    bus = EventBus()
    controller = Controller(BoardMapper(board), engine, bus=bus)

    bus.publish(MouseClickEvent(x=50, y=50))

    assert controller._selected == Position(0, 0)


def test_mouse_jump_event_triggers_the_same_jump_logic():
    board = Board(4, 4)
    board.add_piece(Piece(id=1, color='w', kind='R', cell=Position(0, 0)))
    engine = FakeGameEngine(board)
    bus = EventBus()
    # Mirrors real GameEngine's own self-subscription (engine/game_engine.py)
    # so this fake still completes the full pipeline end-to-end over the bus.
    bus.subscribe(JumpRequestedEvent, lambda event: engine.request_jump(event.source))
    controller = Controller(BoardMapper(board), engine, bus=bus)

    bus.publish(MouseJumpEvent(x=50, y=50))

    assert engine.jump_calls == [Position(0, 0)]


def test_with_bus_move_requested_event_is_published_instead_of_calling_engine_directly():
    board = Board(4, 4)
    board.add_piece(Piece(id=1, color='w', kind='R', cell=Position(0, 0)))
    engine = FakeGameEngine(board)
    bus = EventBus()
    received = []
    bus.subscribe(MoveRequestedEvent, received.append)
    controller = Controller(BoardMapper(board), engine, bus=bus)

    controller.click(50, 50)            # select (0,0)
    result = controller.click(350, 50)  # second click -> (0,3)

    assert result.outcome == "move_requested"
    assert result.move_result is None
    assert engine.calls == []  # Controller no longer calls engine directly
    assert received == [MoveRequestedEvent(source=Position(0, 0), destination=Position(0, 3))]


def test_with_bus_jump_requested_event_is_published_instead_of_calling_engine_directly():
    board = Board(4, 4)
    board.add_piece(Piece(id=1, color='w', kind='R', cell=Position(0, 0)))
    engine = FakeGameEngine(board)
    bus = EventBus()
    received = []
    bus.subscribe(JumpRequestedEvent, received.append)
    controller = Controller(BoardMapper(board), engine, bus=bus)

    result = controller.jump(50, 50)

    assert result.outcome == "jump_requested"
    assert result.move_result is None
    assert engine.jump_calls == []  # Controller no longer calls engine directly
    assert received == [JumpRequestedEvent(source=Position(0, 0))]
