"""
Motion / ArrivalEvent: small data holders for "a piece is currently
travelling", and "a piece just arrived, here is what happened".

WHY DATACLASSES HERE TOO (same reasoning as moves.py in the old project):
The old files.zip project already identified this problem correctly in
its own comment: raw dicts (move['from_r'], move['arrival_time']) have no
fixed shape, any code anywhere can read or write any key, and a typo in a
key name fails silently instead of raising. A @dataclass fixes the field
list once, so `Motion(piece_id=..., source=..., ...)` fails loudly (a
TypeError) if a field is misspelled or missing, and `motion.covers_cell()`
lives on the object instead of being re-written inline at every call site
that needs it.

WHY Motion CARRIES piece_id RATHER THAN A Piece REFERENCE:
Storing a live Piece reference would let RealTimeArbiter accidentally
mutate a Piece's `.cell` mid-flight (before arrival), which would violate
the "board changes only on arrival" rule (Section 10 of the guide) since
the renderer/BoardPrinter reads current `.cell` off the piece. Storing
just the immutable `piece_id` forces RealTimeArbiter to go back through
Board.piece_by_id() at arrival time to make the *one* authorized mutation,
and makes it impossible to move a piece "by accident" from inside Motion.

WHY THIS FILE EXISTS SEPARATELY FROM real_time_arbiter.py:
Motion/ArrivalEvent are plain data with a couple of query methods; the
arbiter is the behavior that creates, advances and resolves them. Keeping
data and behavior in separate small files (rather than one large
real_time_arbiter.py) mirrors the same split already used for
model/piece.py vs rules/piece_rules.py: data structures a whole layer
shares stay in their own file so multiple layers can import just the
shape without importing arbiter logic.
"""

from dataclasses import dataclass
from typing import Optional

from kungfu_chess.model.position import Position


@dataclass
class Motion:
    """One piece, currently travelling from source to destination."""
    piece_id: int
    source: Position
    destination: Position
    start_time_ms: int
    arrival_time_ms: int

    def has_arrived_by(self, now_ms: int) -> bool:
        return now_ms >= self.arrival_time_ms


@dataclass
class ArrivalEvent:
    """Reported by RealTimeArbiter.advance_time() for every motion that
    resolved during that time step, so GameEngine can react (e.g. detect
    a king capture) without RealTimeArbiter needing to know what a king
    is."""
    piece_id: int
    source: Position
    destination: Position
    captured_piece_id: Optional[int]
    captured_kind: Optional[str]
