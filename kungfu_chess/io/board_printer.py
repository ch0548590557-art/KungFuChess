"""
BoardPrinter: Board -> the exact row-text format `print board` compares
against in integration tests.

WHY THIS IS A SEPARATE CLASS FROM Board.row_tokens():
Board.row_tokens() returns raw data (a grid of 2-char strings) because
that's a natural projection of Board's own occupancy - it doesn't need to
know about the space-separated, newline-joined *text format* that
happens to be this course's chosen output convention. BoardPrinter owns
that formatting decision. If a future assignment wanted a different
output format (e.g. comma-separated, or JSON), only BoardPrinter would
change; Board and its tests stay untouched. This is the same
"read-only text I/O adapter, not test-only helper" role BoardParser
plays in reverse (Section 13).

WHY IT TAKES A Board DIRECTLY (NOT A GameSnapshot):
GameSnapshot (engine/game_engine.py) is deliberately a *rendering* DTO -
pixel-oriented piece state for the Renderer. BoardPrinter's job is
strictly "logical occupancy as text", which is exactly what Board already
exposes without any pixel/animation concerns. Routing BoardPrinter through
GameSnapshot would couple text-test correctness to renderer DTO shape for
no benefit.
"""

from kungfu_chess.model.board import Board


class BoardPrinter:
    def print_board(self, board: Board) -> str:
        rows = board.row_tokens()
        return "\n".join(" ".join(row) for row in rows)
