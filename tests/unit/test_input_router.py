from kungfu_chess.model.board import Board
from kungfu_chess.model.piece import Piece
from kungfu_chess.model.position import Position
from kungfu_chess.input.board_mapper import BoardMapper
from kungfu_chess.input.controller import Controller
from kungfu_chess.input.input_router import InputRouter
from kungfu_chess.graphics.board_geometry import BoardGeometry
from kungfu_chess.engine.game_engine import MoveResult


class FakeGameEngine:
    """Same style as test_controller.py's FakeGameEngine: a minimal stand-in
    so these tests only prove InputRouter/Controller wiring, not RuleEngine
    or RealTimeArbiter correctness."""

    def __init__(self, board):
        self.board = board
        self.move_calls = []
        self.jump_calls = []

    def request_move(self, source, destination):
        self.move_calls.append((source, destination))
        return MoveResult(True, "ok")

    def request_jump(self, source):
        self.jump_calls.append(source)
        return MoveResult(True, "ok")


def build(board_offset=(0, 0), enabled=True, window_ms=300):
    board = Board(4, 4)
    board.add_piece(Piece(id=1, color='w', kind='R', cell=Position(0, 0)))
    engine = FakeGameEngine(board)
    controller = Controller(BoardMapper(board), engine)
    geometry = BoardGeometry(cell_size_px=100)
    router = InputRouter(controller, geometry, board_offset=board_offset,
                          enabled=enabled, double_click_window_ms=window_ms)
    return router, controller, engine


def test_single_click_does_nothing_immediately():
    router, controller, engine = build()

    router.on_mouse_down(50, 50, now_ms=0)

    assert controller._selected is None
    assert engine.move_calls == []
    assert engine.jump_calls == []


def test_single_click_commits_only_after_tick_past_window():
    router, controller, engine = build(window_ms=300)

    router.on_mouse_down(50, 50, now_ms=0)
    router.tick(now_ms=200)  # still inside the window
    assert controller._selected is None

    router.tick(now_ms=301)  # window elapsed
    assert controller._selected == Position(0, 0)


def test_double_click_same_cell_within_window_sends_jump_not_move():
    router, controller, engine = build(window_ms=300)

    router.on_mouse_down(50, 50, now_ms=0)
    router.on_mouse_down(60, 60, now_ms=100)  # still (0,0), within window

    assert engine.jump_calls == [Position(0, 0)]
    assert engine.move_calls == []
    assert controller._selected is None  # never committed as a plain click


def test_two_clicks_on_different_cells_within_window_replaces_pending():
    router, controller, engine = build(window_ms=300)
    engine.board.add_piece(Piece(id=2, color='w', kind='R', cell=Position(0, 3)))

    router.on_mouse_down(50, 50, now_ms=0)      # cell (0,0), becomes pending
    router.on_mouse_down(350, 50, now_ms=100)   # cell (0,3), different -> replaces pending

    assert engine.jump_calls == []
    assert controller._selected is None  # neither click committed yet

    router.tick(now_ms=350)  # only 250ms since the *replacing* click -> still pending
    assert controller._selected is None

    router.tick(now_ms=401)  # 301ms since the replacing click -> now it commits
    assert controller._selected == Position(0, 3)


def test_double_click_after_window_elapsed_is_two_separate_clicks():
    router, controller, engine = build(window_ms=300)

    router.on_mouse_down(50, 50, now_ms=0)
    router.tick(now_ms=400)  # first click commits as a plain select
    assert controller._selected == Position(0, 0)

    router.on_mouse_down(60, 60, now_ms=450)  # second click, same cell, but late
    router.tick(now_ms=800)

    assert engine.jump_calls == []  # never treated as a double-click


def test_board_offset_is_subtracted_before_reaching_controller():
    router, controller, engine = build(board_offset=(200, 40), window_ms=300)

    # window pixel (250, 90) - offset (200, 40) = board pixel (50, 50) -> (0,0)
    router.on_mouse_down(250, 90, now_ms=0)
    router.tick(now_ms=400)

    assert controller._selected == Position(0, 0)


def test_observer_mode_never_reaches_controller_even_for_double_click():
    router, controller, engine = build(enabled=False, window_ms=300)

    router.on_mouse_down(50, 50, now_ms=0)
    router.on_mouse_down(60, 60, now_ms=100)  # would otherwise be a jump
    router.tick(now_ms=1000)

    assert controller._selected is None
    assert engine.jump_calls == []
    assert engine.move_calls == []


def test_click_outside_the_board_does_not_raise():
    router, controller, engine = build(window_ms=300)

    router.on_mouse_down(10_000, 10_000, now_ms=0)
    router.tick(now_ms=400)

    assert controller._selected is None
    assert engine.move_calls == []
    assert engine.jump_calls == []
