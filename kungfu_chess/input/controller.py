"""
Controller: converts a raw pixel click into, at most, one call to
GameEngine.request_move. It holds selection state and nothing else -
no chess legality, no Board mutation (Section 11).

WHY SELECTION LIVES HERE AND NOT IN GameEngine OR Board:
"What cell did the user click first" is purely an input-interpretation
concept - it has no meaning to chess rules, to Board's occupancy, or to
RealTimeArbiter's timers. If GameEngine owned it, GameEngine would grow
an input-shaped responsibility it doesn't need for the text-test path
(TextTestRunner drives GameEngine directly for `wait`/`print board`, but
still goes through Controller for `click`, precisely so this state stays
in one place regardless of which caller is clicking).

WHY THE OUTSIDE-BOARD / EMPTY-CELL POLICY IS ENCODED AS PLAIN IF/ELSE
RATHER THAN A STATE-MACHINE LIBRARY:
The whole policy is four short rules (Section 11), each independently
simple: ignore an outside click with nothing selected; cancel selection
on an outside click with something selected; select on a first click on
an occupied cell; forward to GameEngine and always clear selection on any
second in-board click. A dedicated state-machine abstraction would be
solving a problem this class doesn't have - four branches read
completely at a glance, and the "always clear selection after a second
in-board click, legal or not" rule (Section 2 test list) is easiest to
guarantee by literally always clearing it in that one branch, rather than
threading a "did I clear it yet" flag through library callback hooks.

WHY THIS RETURNS A SMALL ControllerResult INSTEAD OF THE RAW
MoveResult/None:
A click can end in several distinct outcomes for a caller that wants to
know what happened (selected / cleared / forwarded-to-engine /ignored).
Returning GameEngine's MoveResult directly would be `None` for three of
those four outcomes, forcing every caller to guess which kind of "did
nothing" happened. A tiny dedicated result keeps Controller's own unit
tests (Iteration 2, Section 16: "Controller Unit tests with a fake
GameEngine") readable without reaching into GameEngine internals.
"""

from dataclasses import dataclass
from typing import Optional

from kungfu_chess.model.position import Position
from kungfu_chess.input.board_mapper import BoardMapper
from kungfu_chess.engine.game_engine import GameEngine, MoveResult


@dataclass
class ControllerResult:
    outcome: str                      # "ignored" | "selected" | "cleared" | "move_requested"
    move_result: Optional[MoveResult] = None


class Controller:
    def __init__(self, mapper: BoardMapper, engine: GameEngine):
        self._mapper = mapper
        self._engine = engine
        self._selected: Optional[Position] = None

    def click(self, x: int, y: int) -> ControllerResult:
        pos = self._mapper.pixel_to_cell(x, y)

        if pos is None:
            if self._selected is None:
                return ControllerResult("ignored")
            self._selected = None
            return ControllerResult("cleared")

        if self._selected is None:
            piece = self._engine.board.piece_at(pos)
            if piece is None:
                return ControllerResult("ignored")
            self._selected = pos
            return ControllerResult("selected")

        source = self._selected
        self._selected = None
        result = self._engine.request_move(source, pos)
        return ControllerResult("move_requested", move_result=result)
