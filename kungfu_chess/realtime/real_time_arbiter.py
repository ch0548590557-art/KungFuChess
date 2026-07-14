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

from typing import List, Optional, Set

from kungfu_chess.model.position import Position
from kungfu_chess.model.board import Board
from kungfu_chess.model.piece import Piece, PieceState
from kungfu_chess.realtime.motion import Motion, ArrivalEvent, MotionKind
from kungfu_chess.realtime.collision_resolver import CollisionResolver
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

    def start_motion(self, piece: Piece, destination: Position, now_ms: int,
                     action_kind: str = MotionKind.MOVE) -> None:
        if action_kind == MotionKind.JUMP:
            duration_ms = config.JUMP_DURATION_MS
        else:
            steps = max(abs(destination.row - piece.cell.row),
                        abs(destination.col - piece.cell.col))
            duration_ms = steps * _CELL_DURATION_MS

        motion = Motion(
            piece_id=piece.id,
            source=piece.cell,
            destination=destination,
            start_time_ms=now_ms,
            arrival_time_ms=now_ms + duration_ms,
            action_kind=action_kind,
        )

        self._active_motions.append(motion)

        if action_kind == MotionKind.JUMP:
            piece.state = PieceState.JUMPING
        else:
            piece.state = PieceState.MOVING

    def start_jump(self, piece: Piece, now_ms: int, board: Board) -> None:
        board.detach_piece(piece.cell)
        self.start_motion(piece, piece.cell, now_ms, action_kind=MotionKind.JUMP)

    def advance_time(self, board: Board, target_time_ms: int) -> List[ArrivalEvent]:
        arrived = [m for m in self._active_motions if m.has_arrived_by(target_time_ms)]
        arrived.sort(key=lambda m: (
            m.arrival_time_ms,
            0 if m.action_kind == MotionKind.JUMP else 1,
            m.start_time_ms,
        ))

        still_active = [m for m in self._active_motions if not m.has_arrived_by(target_time_ms)]

        arrivals, killed, canceled = CollisionResolver.resolve(arrived)
        for motion in killed:
            killed_piece = board.piece_by_id(motion.piece_id)
            if killed_piece is not None:
                board.remove_piece(killed_piece.cell)
                killed_piece.state = PieceState.CAPTURED

        for motion in canceled:
            canceled_piece = board.piece_by_id(motion.piece_id)
            if canceled_piece is not None:
                canceled_piece.state = PieceState.IDLE

        events: List[ArrivalEvent] = []
        for motion in arrivals:
            if board.piece_by_id(motion.piece_id) is None:
                continue

            event = self._resolve_arrival(board, motion, target_time_ms)
            if event is not None:
                events.append(event)
            else:
                still_active.append(motion)

        self._active_motions = still_active
        return events

    def _resolve_arrival(self, board: Board, motion: Motion,
                         target_time_ms: int) -> Optional[ArrivalEvent]:
        piece = board.piece_by_id(motion.piece_id)
        if piece is None:
            return None

        if motion.action_kind == MotionKind.JUMP:
            captured = board.piece_at(motion.destination)
            captured_id = None
            captured_kind = None
            if captured is not None:
                if captured.color != piece.color:
                    board.remove_piece(motion.destination)
                    captured_id = captured.id
                    captured_kind = captured.kind
                else:
                    # Same-color occupancy blocks landing. Retry on the next
                    # time advance so the jumper stays airborne until the
                    # square becomes available.
                    motion.arrival_time_ms = target_time_ms + 1
                    return None

            board.place_piece(piece)
            piece.state = PieceState.IDLE

            return ArrivalEvent(
                piece_id=piece.id,
                source=motion.source,
                destination=motion.destination,
                captured_piece_id=captured_id,
                captured_kind=captured_kind,
            )

        captured = board.piece_at(motion.destination)
        captured_id = None
        captured_kind = None
        if captured is not None and captured.id != piece.id:
            board.remove_piece(motion.destination)
            captured_id = captured.id
            captured_kind = captured.kind

        board.move_piece(motion.source, motion.destination)
        piece.state = PieceState.IDLE

        return ArrivalEvent(
            piece_id=piece.id,
            source=motion.source,
            destination=motion.destination,
            captured_piece_id=captured_id,
            captured_kind=captured_kind,
        )
