"""
GameState: the small piece of "whole game" state that isn't Board and
isn't a movement rule - currently just game_over (and, if the game ends,
the winning color).

WHY THIS EXISTS AS ITS OWN CLASS INSTEAD OF TWO LOOSE FIELDS ON
GameEngine:
game_over is read by GameEngine.request_move (to short-circuit before
RuleEngine even runs), written by GameEngine after a king-capture arrival
event, and read again by GameSnapshot for the renderer. Grouping it in one
small dataclass instead of scattering `self._game_over` /
`self._winner` directly on GameEngine keeps "whole-game status" separable
from "coordination logic" - GameEngine can be unit-tested by constructing
a GameState directly, without needing a full Board/RuleEngine/Arbiter
wiring just to set `game_over=True`.

WHY A DATACLASS (mutable):
game_over flips from False to True exactly once, in place, when a king is
captured. A dataclass gives us that mutable field with a clean __init__
and no custom code needed.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GameState:
    game_over: bool = False
    winner: Optional[str] = None  # 'w' / 'b', set only when game_over

    def end_game(self, winner_color: str) -> None:
        self.game_over = True
        self.winner = winner_color
