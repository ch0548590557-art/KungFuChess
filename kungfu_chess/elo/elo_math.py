"""
elo_math: pure functions implementing the standard ELO rating formula -
no I/O, no UserRepository, no knowledge of usernames or games. Kept
separate from EloService (which does the I/O: fetching/saving User rows)
so the arithmetic itself can be tested with plain integers/floats, the
same separation notation.py has from GameEngine (a pure computation
module a stateful service calls into, rather than inlining the math
where the state lives).

WHY expected_score()/updated_rating() TAKE A PLAIN actual_score: float
(0.0/0.5/1.0) INSTEAD OF A winner_color STRING:
The ELO formula itself has no concept of "color" - only "did this side
score a win, a draw, or a loss". Keeping color out of this module means
it works unchanged for any two ratings, not just white/black chess
players; EloService is the layer that translates a chess-specific
winner_color into the actual_score numbers this module expects.

WHY updated_rating() round()s TO AN int RATHER THAN RETURNING A float:
UserRepository.update_rating() and the users.rating column are both
integers (Step 1) - returning a float here would just push the same
rounding decision onto every caller instead of making it once, in the
one place that actually knows the formula's output is going to become a
stored ranking, not carried through further math.
"""

DEFAULT_K_FACTOR = 32


def expected_score(rating: int, opponent_rating: int) -> float:
    return 1 / (1 + 10 ** ((opponent_rating - rating) / 400))


def updated_rating(
    rating: int, opponent_rating: int, actual_score: float, k_factor: int = DEFAULT_K_FACTOR,
) -> int:
    expected = expected_score(rating, opponent_rating)
    return round(rating + k_factor * (actual_score - expected))