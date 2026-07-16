"""
Unit-level coverage for app.py, the project's single entry point.

Three things are checked here, deliberately without a subprocess:
  - build_game() wires the five real collaborators together correctly.
  - run_cli() implements the grader's text protocol correctly.
  - main() picks the right mode based on whether stdin is piped.

tests/integration/test_cli_grader.py re-checks run_cli()'s behaviour
end-to-end through a real `python -m kungfu_chess.app` subprocess (the
actual shape a grader invokes it in); this file is the fast, in-process
version of the same protocol so the day-to-day test loop doesn't pay
subprocess cost for every case.
"""

import io

from kungfu_chess import app
from kungfu_chess.app import build_game, run_cli
from kungfu_chess.io.board_parser import BoardParser
from kungfu_chess.io.board_printer import BoardPrinter
from kungfu_chess.input.board_mapper import BoardMapper
from kungfu_chess.input.controller import Controller
from kungfu_chess.input.input_router import InputRouter
from kungfu_chess.engine.game_engine import GameEngine
from kungfu_chess.graphics.game_renderer import GameRenderer
from kungfu_chess.view.renderer import Renderer


def _call_run_cli(text: str) -> str:
    out = io.StringIO()
    run_cli(text, out=out)
    return out.getvalue().strip()


# ---- build_game: composition root wiring ------------------------------

def test_build_game_returns_one_of_each_collaborator():
    rows = [["wK", ".", "."], [".", ".", "."], [".", ".", "."]]

    engine, controller, renderer, printer = build_game(rows)

    assert isinstance(engine, GameEngine)
    assert isinstance(controller, Controller)
    assert isinstance(renderer, Renderer)
    assert isinstance(printer, BoardPrinter)


def test_build_game_parses_the_board_via_the_real_board_parser():
    rows = [["wK", ".", "."], [".", ".", "."], [".", ".", "."]]
    expected_board = BoardParser().parse(rows)

    engine, _, _, printer = build_game(rows)

    assert printer.print_board(engine.board) == printer.print_board(expected_board)


def test_build_game_controller_can_drive_the_real_engine_end_to_end():
    rows = [["wK", ".", "."], [".", ".", "."], [".", ".", "."]]
    engine, controller, _, printer = build_game(rows)

    controller.click(50, 50)     # select wK at (0, 0)
    controller.click(150, 150)   # move to (1, 1)
    engine.wait(1000)

    assert printer.print_board(engine.board) == ". . .\n. wK .\n. . ."


def test_build_game_mapper_matches_a_freshly_constructed_one():
    rows = [["wK", ".", "."], [".", ".", "."], [".", ".", "."]]
    engine, controller, _, _ = build_game(rows)
    reference_mapper = BoardMapper(engine.board)

    assert controller._mapper.pixel_to_cell(50, 50) == reference_mapper.pixel_to_cell(50, 50)


# ---- run_cli: text protocol --------------------------------------------

def test_run_cli_prints_board_unchanged_with_no_commands():
    output = _call_run_cli(
        "Board:\n"
        "wK . . bK\n"
        ". . . .\n"
        "wR . . bR\n"
        "Commands:\n"
        "print board\n"
    )
    assert output == "wK . . bK\n. . . .\nwR . . bR"


def test_run_cli_reports_unknown_token_and_stops():
    output = _call_run_cli(
        "Board:\n"
        "wK xZ\n"
        ". .\n"
        "Commands:\n"
        "print board\n"
    )
    assert output == "ERROR UNKNOWN_TOKEN"


def test_run_cli_reports_row_width_mismatch():
    output = _call_run_cli(
        "Board:\n"
        "wK . .\n"
        ". bK\n"
        "Commands:\n"
    )
    assert output == "ERROR ROW_WIDTH_MISMATCH"


def test_run_cli_executes_click_wait_and_print_board_in_order():
    output = _call_run_cli(
        "Board:\n"
        "wR . .\n"
        "Commands:\n"
        "click 50 50\n"
        "click 250 50\n"
        "wait 2000\n"
        "print board\n"
    )
    assert output == ". . wR"


def test_run_cli_ignores_blank_lines_and_unrecognized_command_lines():
    output = _call_run_cli(
        "Board:\n"
        "wK . .\n"
        ". . .\n"
        ". . .\n"
        "\n"
        "Commands:\n"
        "\n"
        "not_a_real_command\n"
        "print board\n"
    )
    assert output == "wK . .\n. . .\n. . ."


def test_run_cli_supports_multiple_print_board_calls():
    output = _call_run_cli(
        "Board:\n"
        "wR . .\n"
        "Commands:\n"
        "print board\n"
        "click 50 50\n"
        "click 250 50\n"
        "wait 2000\n"
        "print board\n"
    )
    assert output == "wR . .\n. . wR"


# ---- main(): mode selection based on piped vs. interactive stdin ------

class _FakeStdin(io.StringIO):
    def __init__(self, text, is_tty):
        super().__init__(text)
        self._is_tty = is_tty

    def isatty(self):
        return self._is_tty


def test_main_runs_cli_protocol_when_stdin_is_piped(monkeypatch, capsys):
    fake_in = _FakeStdin(
        "Board:\nwR . .\nCommands:\nprint board\n", is_tty=False
    )
    monkeypatch.setattr(app.sys, "stdin", fake_in)

    app.main()

    assert capsys.readouterr().out.strip() == "wR . ."


class _FakeGameWindow:
    """Stand-in for graphics.game_window.GameWindow - proves main()'s
    interactive branch builds and runs a real window around the real
    engine/renderer/input_router, without opening an actual cv2 window
    during the test suite."""
    instances = []

    def __init__(self, engine, renderer, input_router):
        self.engine = engine
        self.renderer = renderer
        self.input_router = input_router
        self.run_called = False
        _FakeGameWindow.instances.append(self)

    def run(self):
        self.run_called = True


def test_main_opens_a_real_game_window_when_stdin_is_a_terminal(monkeypatch):
    fake_in = _FakeStdin("", is_tty=True)
    monkeypatch.setattr(app.sys, "stdin", fake_in)
    _FakeGameWindow.instances = []
    monkeypatch.setattr(app, "GameWindow", _FakeGameWindow)

    app.main()

    assert len(_FakeGameWindow.instances) == 1
    window = _FakeGameWindow.instances[0]
    assert window.run_called is True
    assert isinstance(window.engine, GameEngine)
    assert isinstance(window.renderer, GameRenderer)
    assert isinstance(window.input_router, InputRouter)
    # Sanity check that the real starting position was actually wired in.
    assert window.engine.board.width == 8
    assert window.engine.board.height == 8
