"""
EloService: recomputes and persists both players' ratings after a
finished game, using the standard ELO formula (elo_math.py) over
User rows fetched/saved through UserRepository - the same repository
AuthService already uses, so a rating update and a login both ultimately
touch the same users table through the one interface allowed to know
about it.

WHY record_game_result() TAKES winner_color: Optional[str] ('w' | 'b' |
None FOR A DRAW) RATHER THAN SEPARATE win()/draw() METHODS:
The ELO math itself is a single formula parameterized by an actual score
(elo_math.py) - splitting the caller-facing API into multiple methods
would just re-implement that same win/draw/loss -> score branch at a
second layer for no benefit. GameEngine cannot currently produce a draw
(only king-capture ends a game - see bus/events.py's GameEndedEvent), so
winner_color is never actually None on the live GameSession path today,
but the formula supports it for free, and it's what makes this module's
own draw-scenario tests possible to write at all without a second code
path that would go untested by anything except those tests.

WHY THIS RAISES (UnknownPlayerError) IF EITHER USERNAME DOESN'T RESOLVE
TO A USER, RATHER THAN SILENTLY SKIPPING THE UPDATE:
By the time GameSession (network layer) ever calls this, both usernames
came from SessionManager.username_for_role() - names that only got set
by a successful AuthService.register()/authenticate() call, which always
means a real row exists in this same UserRepository. A missing user here
would mean that invariant broke somewhere else; silently skipping the
rating update would hide that bug instead of surfacing it.
"""

from typing import Optional, Tuple

from kungfu_chess.auth.user_repository import UserRepository
from kungfu_chess.elo import elo_math


class UnknownPlayerError(Exception):
    def __init__(self, username: str):
        super().__init__(f"no such user: {username}")
        self.username = username


class EloService:
    def __init__(self, user_repository: UserRepository, k_factor: int = elo_math.DEFAULT_K_FACTOR):
        self._repository = user_repository
        self._k_factor = k_factor

    def record_game_result(
        self, white_username: str, black_username: str, winner_color: Optional[str],
    ) -> None:
        white = self._repository.get_by_username(white_username)
        if white is None:
            raise UnknownPlayerError(white_username)
        black = self._repository.get_by_username(black_username)
        if black is None:
            raise UnknownPlayerError(black_username)

        white_score, black_score = _scores_for(winner_color)
        new_white_rating = elo_math.updated_rating(white.rating, black.rating, white_score, self._k_factor)
        new_black_rating = elo_math.updated_rating(black.rating, white.rating, black_score, self._k_factor)

        self._repository.update_rating(white.id, new_white_rating)
        self._repository.update_rating(black.id, new_black_rating)


def _scores_for(winner_color: Optional[str]) -> Tuple[float, float]:
    if winner_color == 'w':
        return 1.0, 0.0
    if winner_color == 'b':
        return 0.0, 1.0
    if winner_color is None:
        return 0.5, 0.5
    raise ValueError(f"unknown winner_color: {winner_color!r}")