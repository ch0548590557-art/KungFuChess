"""Small data holders for in-flight state.

These replace the raw dicts (move['from_r'], jump['end_time'], ...) that
were being built and read in several different places in the original
script. A dict has no "shape" - any code anywhere can read or write any
key, and typos in keys fail silently. A dataclass has named, fixed fields,
and behavior that belongs to the move/jump (like "does this move start at
this square?") lives on the object itself instead of being re-written
inline every time it's needed.
"""

from dataclasses import dataclass


@dataclass
class PendingMove:
    """A move that has been queued (via 'click') but hasn't arrived yet."""
    arrival_time: int
    from_r: int
    from_c: int
    to_r: int
    to_c: int
    piece: str

    def starts_at(self, r, c):
        return self.from_r == r and self.from_c == c


@dataclass
class AirborneJump:
    """A piece that is temporarily 'in the air' (via 'jump') and can be
    captured mid-flight by a move that lands on its square while it's
    still airborne."""
    row: int
    col: int
    start_time: int
    end_time: int
    piece: str

    def covers(self, r, c, at_time):
        return self.row == r and self.col == c and self.start_time <= at_time <= self.end_time

    def is_enemy_of(self, piece):
        return self.piece[0] != piece[0]

    def is_active_after(self, time):
        return self.end_time > time
