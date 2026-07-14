"""
Piece: identity + classification + current logical cell + lifecycle flag.

WHY A DATACLASS (mutable, not frozen):
Unlike Position, a Piece genuinely changes over its lifetime: it moves
(cell changes), it starts/finishes moving (state changes), it can be
captured (state changes again). A frozen dataclass would force us to
throw away and rebuild a Piece object on every arrival, and then every
other structure holding a reference to "that piece" (e.g. an active
Motion in RealTimeArbiter, Section 10) would suddenly point at a stale
object. A plain mutable @dataclass gives us named fields with a generated
__init__/__repr__, while still allowing `piece.cell = new_cell`.

WHY PieceState IS A SEPARATE ENUM AND NOT A STRING:
Using bare strings ("idle", "moving", "captured") invites typos that
Python won't catch until runtime ("mvoing" silently never matches
anything). An Enum makes illegal states a NameError/AttributeError at the
call site instead of a silent logic bug, and IDEs can autocomplete the
valid values.

WHY STATE HOLDS FOUR VALUES (IDLE / MOVING / CAPTURED / JUMPING):
The design guide is explicit (Section 6): Piece.state is a *lifecycle*
flag only. It must NOT store destination, path, elapsed time, speed, or
interpolation - all of that is Motion's job (realtime/motion.py). This
keeps Piece a small, stable object that RuleEngine, PieceRules and
RealTimeArbiter can all reason about without needing to know about each
other's timing details. JUMPING was added for the "Jump" extra-route
ability: it is deliberately its own value rather than reusing MOVING,
because the two states mean different things to a piece arriving at that
cell - a MOVING piece is just "somewhere mid-flight, hasn't been resolved
yet" and gets captured normally like an IDLE piece; a JUMPING piece is
"currently untouchable and about to capture whatever grounded piece
arrives here", the opposite outcome. Collapsing them into one value would
force every arrival-resolution check to also inspect *which kind* of
Motion produced that state, spreading the distinction across two objects
instead of keeping it as one flag on Piece.

WHY id IS A SEPARATE FIELD FROM cell:
Two pieces can (temporarily, mid-swap in a hypothetical rule) target the
same cell, and a piece's cell changes over time - so cell cannot serve as
a stable identity. A dedicated id lets RealTimeArbiter say "the motion
belonging to piece #7" even while piece #7's cell field is being updated,
which is exactly what the extra-route "simultaneous movement" feature
needs (Iteration 10): multiple Motions must each track a *specific*
piece, not "whatever is currently on this square".
"""

from dataclasses import dataclass
from enum import Enum, auto

from kungfu_chess.model.position import Position


class PieceState(Enum):
    IDLE = auto()
    MOVING = auto()
    CAPTURED = auto()
    JUMPING = auto()


@dataclass
class Piece:
    id: int
    color: str          # 'w' or 'b'
    kind: str            # one of config.VALID_KINDS
    cell: Position
    state: PieceState = PieceState.IDLE
    has_moved: bool = False

    def is_enemy_of(self, other: "Piece") -> bool:
        return self.color != other.color
