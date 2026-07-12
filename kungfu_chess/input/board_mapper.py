"""
BoardMapper: the only class in the codebase that knows pixels exist.

WHY THIS IS ITS OWN CLASS RATHER THAN A FUNCTION INSIDE Controller:
Section 19 names this exact question ("Ask the LLM to compare possible
ownership of pixel-to-cell mapping") as a teaching moment. Putting pixel
math inside Controller would work today, but Controller also owns
selection state and command dispatch - two concerns that have nothing to
do with *how many pixels make a square*. Keeping BoardMapper separate
means: (1) it can be unit-tested with nothing but two integers and a
board size, no Controller/GameEngine fixture required, and (2) the extra
route's "viewport/scrolling camera" note (Section 11) has an obvious,
already-isolated place to change the mapping formula without touching
Controller at all.

WHY IT RETURNS Optional[Position] (None FOR OUT-OF-BOUNDS) INSTEAD OF
RAISING:
An out-of-bounds click is an expected, routine outcome of normal mouse
input - a user's cursor drifting past the board edge is not a bug, so
it shouldn't be an exception. Controller treats `None` as an ordinary
branch (Section 11: "ignore" or "cancel selection", depending on
whether something was already selected), which reads more naturally as
an `if pos is None:` check than a try/except around every click.
"""

from typing import Optional

from kungfu_chess.model.position import Position
from kungfu_chess.model.board import Board
import kungfu_chess.config as config


class BoardMapper:
    def __init__(self, board: Board):
        self._board = board

    def pixel_to_cell(self, x: int, y: int) -> Optional[Position]:
        col = x // config.CELL_SIZE_PX
        row = y // config.CELL_SIZE_PX
        pos = Position(row, col)
        return pos if self._board.in_bounds(pos) else None
