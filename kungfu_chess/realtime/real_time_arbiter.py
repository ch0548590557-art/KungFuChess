"""
RealTimeArbiter: owns the collection of in-flight Motions, advances
simulated time, and resolves arrivals (capture + placement + king-capture
reporting). Board never stores motion state (Section 10) - it only holds
logical occupancy - so all "who is currently travelling" state lives here
and only here.

--- Iteration 10 / extra route: "Simultaneous movement of multiple pieces"

ARCHITECTURE IMPACT NOTE (written before implementation, per Section 10's
"Extra-route implementation rule" and Section 17's guidance to write this
before coding):

  Affected layers:
    - RealTimeArbiter: was already storing a *list* of motions (nothing
      to change in the data structure itself), but its start-gate needs
      to allow more than one entry in that list at once.
    - GameEngine: the common-route guard that rejected a second move with
      reason "motion_in_progress" whenever ANY motion was active is
      replaced by a narrower, always-correct guard: a piece cannot start
      a second motion while it is already moving. Two *different* pieces
      moving at the same time is now allowed.

  New state required:
    - None beyond what RealTimeArbiter already needed for the common
      route (a list of Motion, not a single Optional[Motion]). The only
      new thing is a concurrency *limit*, which is a config knob
      (config.MAX_CONCURRENT_MOTIONS), not new runtime state.

  Public API impact:
    - has_active_motion() keeps its old meaning ("is anything moving at
      all") for backward compatibility / for reproducing common-route
      behaviour when the cap is set to 1.
    - A new method, can_start_motion(piece_id), is added rather than
      overloading has_active_motion(), because the two questions
      ("is *anything* moving" vs "can *this piece* start moving") are
      genuinely different questions with different answers once more
      than one motion can be active. GameEngine now calls
      can_start_motion() instead of has_active_motion() when deciding
      whether to accept request_move().

  Tests required:
    - Two different pieces can both be mid-motion at once (new).
    - The same piece cannot be given a second motion while its first one
      is still active (unchanged rule, now piece-scoped not global).
    - Setting config.MAX_CONCURRENT_MOTIONS = 1 reproduces the exact old
      common-route behaviour, proving the extra feature is additive, not
      a rewrite.
    - Arrivals of two simultaneous motions in the same advance_time()
      call are each resolved correctly and independently.

  Layers that must remain unchanged:
    - Board: still only stores logical occupancy; still knows nothing
      about Motion.
    - RuleEngine / PieceRules: legality of a single move never depended
      on how many *other* pieces are mid-flight, so nothing here changes.
    - Controller: still just forwards (source, destination) to
      GameEngine; it has no opinion on concurrency.

WHY A SINGLE CONFIG NUMBER (config.MAX_CONCURRENT_MOTIONS) INSTEAD OF A
HARD-CODED "unlimited" OR A SEPARATE "SimultaneousArbiter" SUBCLASS:
The requirement was "make the code flexible". A subclass
(RealTimeArbiter vs SimultaneousRealTimeArbiter) would mean GameEngine
has to be told *which class* to construct, spreading the decision across
two files. A boolean flag ("simultaneous_allowed: bool") would only ever
support two states. A single Optional[int] limit supports all three
useful configurations (1 = original common route, N = capped concurrency
for tuning/testing, None = fully unlimited extra route) behind one
constructor parameter, with zero new code paths - can_start_motion() has
exactly one branch that reads the limit, not one branch per mode.
"""

from typing import List, Optional

from kungfu_chess.model.position import Position
from kungfu_chess.model.board import Board
from kungfu_chess.model.piece import Piece, PieceState
from kungfu_chess.realtime.motion import Motion, ArrivalEvent, MotionKind
import kungfu_chess.config as config

_CELL_DURATION_MS = int(
    config.CELL_SIZE_PX / config.PIECE_SPEED_PX_PER_SEC * 1000
)


class RealTimeArbiter:
    def __init__(self, max_concurrent_motions: Optional[int] = config.MAX_CONCURRENT_MOTIONS):
        self._active_motions: List[Motion] = []
        self._max_concurrent = max_concurrent_motions

    # ---- queries -----------------------------------------------------

    def has_active_motion(self) -> bool:
        """True if *anything at all* is currently moving. Kept for
        common-route parity / callers that only care about the global
        state, not a specific piece."""
        return len(self._active_motions) > 0

    def is_piece_moving(self, piece_id: int) -> bool:
        return any(m.piece_id == piece_id for m in self._active_motions)

    def can_start_motion(self, piece_id: int) -> bool:
        if self.is_piece_moving(piece_id):
            return False
        if self._max_concurrent is not None and len(self._active_motions) >= self._max_concurrent:
            return False
        return True

    # ---- mutation ------------------------------------------------------

    def start_motion(self, piece: Piece, destination: Position, now_ms: int) -> None:
        steps = max(abs(destination.row - piece.cell.row),
                    abs(destination.col - piece.cell.col))
        duration_ms = steps * _CELL_DURATION_MS

        self._active_motions.append(Motion(
            piece_id=piece.id,
            source=piece.cell,
            destination=destination,
            start_time_ms=now_ms,
            arrival_time_ms=now_ms + duration_ms,
        ))
        piece.state = PieceState.MOVING

    def start_jump(self, piece: Piece, now_ms: int) -> None:
        """Extra-route "Jump" ability: the piece stays on its own cell
        (source == destination - it never actually travels anywhere) but
        becomes untouchable for config.JUMP_DURATION_MS. This is stored
        as an ordinary Motion in the same _active_motions list as WALK
        motions (rather than a separate tracking structure) precisely so
        it goes through the same can_start_motion() piece-scoped /
        concurrency-capped gate, and the same advance_time() arrival loop,
        as every other kind of travel - the only thing that varies is
        `kind=MotionKind.JUMP`, which _resolve_arrival() below inspects to
        decide how to resolve a collision at this piece's cell.
        """
        self._active_motions.append(Motion(
            piece_id=piece.id,
            source=piece.cell,
            destination=piece.cell,
            start_time_ms=now_ms,
            arrival_time_ms=now_ms + config.JUMP_DURATION_MS,
            kind=MotionKind.JUMP,
        ))
        piece.state = PieceState.JUMPING

    def advance_time(self, board: Board, target_time_ms: int) -> List[ArrivalEvent]:
        arrived = [m for m in self._active_motions if m.has_arrived_by(target_time_ms)]
        # Tie-break same-tick arrivals so WALK motions resolve before JUMP
        # motions: if a jump and an incoming walk both land at the exact
        # same millisecond (as in the "airborne piece captures arriving
        # enemy" fixture, where a 1-cell walk and a jump both take exactly
        # config.JUMP_DURATION_MS / one cell-crossing), the jumping piece
        # must still be JUMPING when the walk is resolved against it - if
        # the jump resolved (and landed, reverting to IDLE) first, the
        # airborne-defense rule below would never see it as airborne at
        # all, purely because of insertion order rather than game logic.
        arrived.sort(key=lambda m: (m.arrival_time_ms, m.kind is MotionKind.JUMP))

        still_active = [m for m in self._active_motions if not m.has_arrived_by(target_time_ms)]

        events = [self._resolve_arrival(board, motion) for motion in arrived]
        events = [event for event in events if event is not None]

        self._active_motions = still_active
        return events

    def _resolve_arrival(self, board: Board, motion: Motion) -> Optional[ArrivalEvent]:
        piece = board.piece_by_id(motion.piece_id)
        if piece is None:
            # This piece was captured by another motion that already
            # resolved earlier in this same advance_time() batch (an
            # airborne mid-flight collision, e.g. two pieces swapping
            # squares and arriving at the same tick). Whichever motion
            # is resolved first "wins"; this motion's piece no longer
            # exists, so it simply vanishes instead of completing.
            return None

        defender = board.piece_at(motion.destination)

        if (
            defender is not None
            and defender.id != piece.id
            and defender.state is PieceState.JUMPING
            and motion.kind is not MotionKind.JUMP
        ):
            # Extra-route "Jump" rule: an airborne (JUMPING) piece is
            # immune to capture and instead captures whichever grounded
            # WALK piece arrives at its cell during the jump window. The
            # defender does not move and stays JUMPING - it will land
            # normally later when its own jump Motion resolves. The
            # arriving piece is removed from wherever Board currently has
            # it recorded, which is always motion.source: Board only ever
            # mutates occupancy on arrival (Section 10), so an in-flight
            # WALK piece is still sitting at its source cell right up
            # until this exact resolution.
            board.remove_piece(motion.source)
            return ArrivalEvent(
                piece_id=defender.id,
                source=defender.cell,
                destination=defender.cell,
                captured_piece_id=piece.id,
                captured_kind=piece.kind,
            )

        captured_id = None
        captured_kind = None
        if defender is not None and defender.id != piece.id:
            board.remove_piece(motion.destination)
            captured_id = defender.id
            captured_kind = defender.kind

        board.move_piece(motion.source, motion.destination)
        piece.state = PieceState.IDLE

        return ArrivalEvent(
            piece_id=piece.id,
            source=motion.source,
            destination=motion.destination,
            captured_piece_id=captured_id,
            captured_kind=captured_kind,
        )
