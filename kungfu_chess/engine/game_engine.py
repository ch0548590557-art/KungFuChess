"""
GameEngine: the public command boundary used by both Controller (real
input) and TextTestRunner (scripted input). It coordinates Board,
RuleEngine and RealTimeArbiter but contains none of their logic itself
(Section 9) - it only decides *when* to call each of them and what to do
with the answer.

WHY GameEngine EXISTS AS A SEPARATE OBJECT FROM RealTimeArbiter/RuleEngine
RATHER THAN FOLDING request_move INTO ONE OF THEM:
RuleEngine only knows "is this move legal by chess rules". RealTimeArbiter
only knows "motions and timers". Neither one alone can answer
"should this request be accepted *right now*", because that answer also
depends on facts neither owns: is the game already over
(GameState, a third object) and is this specific piece already mid-motion
(a RealTimeArbiter fact, but combined with a GameState fact). GameEngine
is the Application Service (Section 5's pattern table) that is allowed to
know about all three collaborators and sequence the guard checks in the
right order, while none of the three lower layers is allowed to know
about each other.

WHY THE GUARD ORDER IS game_over -> can_start_motion -> RuleEngine:
Both game_over and "this piece is already moving" are *application-level*
facts that RuleEngine is explicitly forbidden from knowing about (Section
8: "RuleEngine does not know about game_over"). Checking them first means
RuleEngine - the most expensive check, since it walks legal_destinations
- never even runs for a request that was going to be rejected anyway for
a cheaper, unrelated reason. It also keeps MoveResult.reason values for
game_over/motion-related rejections completely separate from RuleEngine's
own vocabulary (outside_board, illegal_piece_move, ...), so a test can
tell at a glance which layer produced a given rejection.

WHY request_move USES can_start_motion(piece.id) INSTEAD OF THE OLD
has_active_motion() (Iteration 10 change):
This is the one line that turns on "simultaneous movement". The common
route rejected *any* second move while *anything* was moving
(has_active_motion()). The extra-route requirement is that different
pieces may move at the same time, but the same piece obviously still
can't be sent on two motions at once - can_start_motion() is
piece-scoped and reads the concurrency cap from RealTimeArbiter's config
knob, so this one substitution is the entire feature at the GameEngine
level (see the longer architecture note in real_time_arbiter.py).

WHY GameEndedEvent IS PUBLISHED FROM THE SAME wait() BRANCH THAT SETS
GameState.game_over/winner (feature/auth-sqlite-elo, Step 5):
Nothing upstream of GameEngine (network layer, EloService) can observe
game_over flipping to True except by polling GameSnapshot every tick -
publishing an event the moment it happens lets a subscriber (GameSession,
which knows the players' usernames GameEngine deliberately doesn't - see
Section 8) react exactly once, right when it matters, instead of diffing
snapshots. reason was, before resign() existed, always "king_captured"
because that was the only way GameEngine could end a game - see resign()
below for the second way, added exactly as this note predicted: the same
event type, a different reason string.

WHY resign() REUSES GameState.end_game()/GameEndedEvent RATHER THAN A
SEPARATE "GAME ENDED BY RESIGNATION" PATH (feature/matchmaking-disconnect,
Step 4):
A resignation and a king capture are both just "the game is over, here is
who won" from the point of view of everything downstream (request_move's
own game_over guard, GameSession's GameEndedEvent subscription, EloService)
- none of them need to know *why*. Calling the same end_game()/publish()
this class already uses for king_captured, with reason="opponent_disconnected"
instead, means auto-resign (Step 4's driver: a disconnect timer expiring -
see game_session.py) gets every one of those consumers for free instead of
teaching each one a second "game ended" shape.

WHY resign() GUARDS ON game_over INSTEAD OF ASSUMING IT'S ONLY EVER CALLED
ONCE (Step 4):
Two disconnect timers - one per color - can each independently expire
without ever being told the other one already did (see session.py's own
note on why remaining_disconnect_seconds() has to handle both colors
disconnected at once). The guard is what makes calling resign() a second
time, for the side that lost the race, a safe no-op instead of a second
GameEndedEvent overwriting the first winner - and it works with no lock:
resign() does no `await`/yielding of any kind between the game_over check
and end_game()/publish(), and everything that can call it runs on the one
asyncio event loop (same single-threaded reasoning session.py's own
disconnect-timer note already establishes), so two calls can never
actually interleave - the second one's guard always sees the first one's
result, never a half-applied one.

WHY MoveResult IS ITS OWN DATACLASS (mirrors MoveValidation's rationale):
Same reasoning as RuleEngine.MoveValidation: a named result type reads
better than a tuple at call sites (`result.is_accepted` vs `result[0]`),
and gives request_move's contract a stable, greppable name that shows up
in test failures.
"""

from dataclasses import dataclass
from typing import Optional

from kungfu_chess.model.position import Position
from kungfu_chess.model.board import Board
from kungfu_chess.model.game_state import GameState
from kungfu_chess.rules.rule_engine import RuleEngine
from kungfu_chess.rules import promotion_rules
from kungfu_chess.realtime.real_time_arbiter import RealTimeArbiter
from kungfu_chess.engine import notation
from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import (
    GameEndedEvent,
    JumpRequestedEvent,
    MoveCompletedEvent,
    MoveRequestedEvent,
)
import kungfu_chess.config as config


@dataclass
class MoveResult:
    is_accepted: bool
    reason: str


@dataclass
class GameSnapshot:
    board_width: int
    board_height: int
    pieces: list          # list of (kind, color, row, col, state) tuples
    game_over: bool
    winner: str = None
    motions: dict = None
    captures: list = None  # list of (kind, color) tuples, one per piece captured so far this game
    completed_moves: list = None  # list of (color, san, timestamp_ms) tuples, in completion order

class GameEngine:
    def __init__(self, board: Board, rule_engine: RuleEngine = None,
                 arbiter: RealTimeArbiter = None, state: GameState = None,
                 bus: Optional[EventBus] = None):
        self._board = board
        self._rule_engine = rule_engine or RuleEngine()
        self._arbiter = arbiter or RealTimeArbiter()
        self._state = state or GameState()
        self._bus = bus
        self._clock_ms = 0
        self._captures: list = []
        self._completed_moves: list = []
        if bus is not None:
            bus.subscribe(MoveRequestedEvent, lambda event: self.request_move(event.source, event.destination))
            bus.subscribe(JumpRequestedEvent, lambda event: self.request_jump(event.source))

    # ---- public command boundary --------------------------------------

    @property
    def game_over(self) -> bool:
        """Cheap read of the one GameState fact callers outside this
        class occasionally need before deciding whether to act at all
        (feature/matchmaking-disconnect, Step 5: GameSession.login()
        checks this before allowing a reconnect - see its own docstring)
        - deliberately not routed through snapshot(), which walks every
        piece on the board to build a whole GameSnapshot just to answer
        a single bool."""
        return self._state.game_over

    def request_move(self, source: Position, destination: Position) -> MoveResult:
        if self._state.game_over:
            return MoveResult(False, "game_over")

        piece = self._board.piece_at(source)
        if piece is not None and not self._arbiter.can_start_motion(piece.id):
            return MoveResult(False, "motion_in_progress")

        validation = self._rule_engine.validate_move(self._board, source, destination)
        if not validation.is_valid:
            return MoveResult(False, validation.reason)

        self._arbiter.start_motion(piece, destination, self._clock_ms)
        if self._bus is not None:
            self._bus.publish(MoveCompletedEvent(source=source, destination=destination))
        return MoveResult(True, "ok")

    def request_jump(self, source: Position) -> MoveResult:
        """Extra-route "Jump" ability: a piece becomes airborne on its own
        cell for config.JUMP_DURATION_MS (see RealTimeArbiter.start_jump).

        WHY THIS SKIPS RuleEngine ENTIRELY, UNLIKE request_move:
        RuleEngine.validate_move answers "is this a legal *destination* for
        this piece's geometry" (Section 8) - but a jump has no destination
        to validate; it always targets the piece's own current cell. There
        is no chess-geometry question to ask, so involving RuleEngine here
        would mean inventing a fake destination just to satisfy an API that
        doesn't apply. The two guards that DO still apply are exactly the
        application-level ones request_move also checks first, in the same
        order, for the same reason (Section 8: RuleEngine doesn't know
        about game_over; a piece already mid-motion can't start another):
        game_over, then can_start_motion. Reusing can_start_motion (rather
        than a parallel can_start_jump) also means Rule 5 ("a moving piece
        cannot jump") and "a piece already jumping cannot jump again" are
        both enforced for free - a JUMP is stored as a Motion like any
        other, so a piece with one already active fails this same check.
        """
        if self._state.game_over:
            return MoveResult(False, "game_over")

        piece = self._board.piece_at(source)
        if piece is None:
            return MoveResult(False, "empty_cell")
        if not self._arbiter.can_start_motion(piece.id):
            return MoveResult(False, "motion_in_progress")

        self._arbiter.start_jump(piece, self._clock_ms)
        if self._bus is not None:
            self._bus.publish(MoveCompletedEvent(source=source, destination=source, is_jump=True))
        return MoveResult(True, "ok")

    def resign(self, resigning_color: str, reason: str) -> None:
        """Ends the game immediately in favor of whichever color is not
        `resigning_color` - see the module docstring above on why this
        reuses end_game()/GameEndedEvent rather than a separate path, and
        why the game_over guard below is what keeps this safe to call
        twice (once per disconnected color) with no lock."""
        if self._state.game_over:
            return
        winner_color = 'b' if resigning_color == 'w' else 'w'
        self._state.end_game(winner_color=winner_color)
        if self._bus is not None:
            self._bus.publish(GameEndedEvent(winner_color=winner_color, reason=reason))

    def wait(self, ms: int) -> None:
        self._clock_ms += ms
        events = self._arbiter.advance_time(self._board, self._clock_ms)
        for event in events:
            piece = self._board.piece_by_id(event.piece_id)
            moved_kind = piece.kind if piece is not None else None
            is_capture = event.captured_piece_id is not None

            if event.captured_kind == config.KING:
                capturer = self._board.piece_by_id(event.piece_id)
                self._state.end_game(winner_color=capturer.color)
                if self._bus is not None:
                    self._bus.publish(GameEndedEvent(winner_color=capturer.color, reason="king_captured"))
            if is_capture:
                capturer = self._board.piece_by_id(event.piece_id)
                captured_color = 'b' if capturer.color == 'w' else 'w'
                self._captures.append((event.captured_kind, captured_color))

            promoted_to = self._maybe_promote(event)
            self._maybe_record_move(event, piece, moved_kind, is_capture, promoted_to)

    def _maybe_record_move(self, event, piece, moved_kind, is_capture, promoted_to) -> None:
        """Only WALK arrivals that actually changed the piece's cell are
        real chess moves - a Jump lands back on its own cell
        (event.source == event.destination), and so does the defender in
        an airborne-Jump capture (Jump extra-route rule in
        real_time_arbiter.py); neither is a move a SAN log should show."""
        if piece is None or event.source == event.destination:
            return
        san = notation.build_san(
            self._board, piece, moved_kind, event.source, event.destination,
            is_capture, promoted_to,
        )
        self._completed_moves.append((piece.color, san, self._clock_ms))

    def _maybe_promote(self, event) -> "str | None":
        """Pawn promotion is an *arrival-time* consequence (Section 10's
        pattern for king-capture applies equally here): RealTimeArbiter
        only knows about generic motion/capture bookkeeping - it has no
        idea what a pawn or a queen is. GameEngine is the layer allowed to
        know "this arrived" (from the ArrivalEvent), so promotion is
        *checked* right next to the king-capture check that already lives
        here for the same reason.

        WHAT it promotes into - and whether promotion happens at all - is
        deliberately NOT decided here: that's rules/promotion_rules.py's
        job, the same way RuleEngine defers "where can this piece go" to
        piece_rules.PIECE_RULES instead of hard-coding rook geometry
        inline. GameEngine's only remaining responsibility is *timing*
        ("check after every arrival"); a policy change (disable
        promotion, promote to a different kind, add a second promotable
        piece type) is a config.py / promotion_rules.py edit, never a
        GameEngine edit.
        """
        piece = self._board.piece_by_id(event.piece_id)
        if piece is None:
            return None
        target_kind = promotion_rules.promotion_target(self._board, piece)
        if target_kind is not None:
            piece.kind = target_kind
        return target_kind

    def snapshot(self) -> GameSnapshot:
        pieces = [
            (p.kind, p.color, p.cell.row, p.cell.col, p.state.name)
            for p in self._board.all_pieces()
        ]
        motions = {
            (m.source.row, m.source.col):
                (m.destination.row, m.destination.col, m.start_time_ms, m.arrival_time_ms)
            for m in self._arbiter.active_motions()
        }
        return GameSnapshot(
            board_width=self._board.width,
            board_height=self._board.height,
            pieces=pieces,
            game_over=self._state.game_over,
            winner=self._state.winner,
            motions=motions,
            captures=list(self._captures),
            completed_moves=list(self._completed_moves),
        )

    # ---- read-only accessors used by BoardPrinter / tests --------------

    @property
    def board(self) -> Board:
        return self._board
