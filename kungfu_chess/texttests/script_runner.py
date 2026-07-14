"""
ScriptRunner: executes a parsed .kfc script by driving the exact same
public path a real user/UI would use.

WHY IT CALLS Controller.click / GameEngine.wait INSTEAD OF EVER TOUCHING
Board DIRECTLY:
Section 15 names the "forbidden shortcut" explicitly: if ScriptRunner
called Board.move_piece() directly, the test would stop proving that
click -> Controller -> GameEngine -> RuleEngine -> RealTimeArbiter
actually works end to end - a bug in Controller's selection logic, or in
GameEngine's guards, could exist right alongside a perfectly "passing"
suite that quietly bypassed all of it. Every `.kfc` script in this
project is only meaningful as a regression test *because* it goes through
the same door a mouse click would.

WHY A NEW Controller/GameEngine PAIR IS BUILT PER "Board" COMMAND:
A script's `Board` block defines a fresh starting position; building a
new engine/controller pair scoped to that command keeps scripts fully
independent of each other (no leaked selection state or leaked pending
motions from a previous script), and matches how a fresh game actually
starts app-side.

WHY FAILURES ARE COLLECTED (expected vs actual) RATHER THAN RAISING ON
THE FIRST MISMATCH:
A script can contain more than one `print board` (see the guide's
Iteration 6 example: two separate print-board checks in one script). If
the first check fails, later checks might still carry useful diagnostic
information about what stayed wrong or right - collecting all mismatches
and returning them together gives the caller/test framework the complete
picture in one run instead of a fix-one-rerun-repeat loop.
"""

from dataclasses import dataclass, field
from typing import List, Tuple

from kungfu_chess.io.board_parser import BoardParser
from kungfu_chess.io.board_printer import BoardPrinter
from kungfu_chess.input.board_mapper import BoardMapper
from kungfu_chess.input.controller import Controller
from kungfu_chess.engine.game_engine import GameEngine
from kungfu_chess.texttests.script_parser import parse_script


@dataclass
class ScriptResult:
    passed: bool
    failures: List[Tuple[List[str], List[str]]] = field(default_factory=list)


class ScriptRunner:
    def __init__(self, parser: BoardParser = None, printer: BoardPrinter = None):
        self._parser = parser or BoardParser()
        self._printer = printer or BoardPrinter()

    def run(self, script_text: str) -> ScriptResult:
        commands = parse_script(script_text)
        engine = None
        controller = None
        failures = []

        for command in commands:
            kind = command[0]

            if kind == "board":
                board = self._parser.parse(command[1])
                engine = GameEngine(board)
                controller = Controller(BoardMapper(board), engine)

            elif kind == "click":
                controller.click(command[1], command[2])

            elif kind == "jump":
                controller.jump(command[1], command[2])

            elif kind == "wait":
                engine.wait(command[1])

            elif kind == "print":
                expected = [" ".join(row) for row in command[1]]
                actual = self._printer.print_board(engine.board).split("\n")
                if actual != expected:
                    failures.append((expected, actual))

        return ScriptResult(passed=not failures, failures=failures)
