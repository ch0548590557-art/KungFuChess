from kungfu_chess.model.board import Board
from kungfu_chess.model.piece import Piece
from kungfu_chess.model.position import Position
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

    def request_move(self, source, destination):
        self.calls.append((source, destination))
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
