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

WHY MoveResult IS ITS OWN DATACLASS (mirrors MoveValidation's rationale):
Same reasoning as RuleEngine.MoveValidation: a named result type reads
better than a tuple at call sites (`result.is_accepted` vs `result[0]`),
and gives request_move's contract a stable, greppable name that shows up
in test failures.
"""

from dataclasses import dataclass

from kungfu_chess.model.position import Position
from kungfu_chess.model.board import Board
from kungfu_chess.model.game_state import GameState
from kungfu_chess.rules.rule_engine import RuleEngine
from kungfu_chess.realtime.real_time_arbiter import RealTimeArbiter
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


class GameEngine:
    def __init__(self, board: Board, rule_engine: RuleEngine = None,
                 arbiter: RealTimeArbiter = None, state: GameState = None):
        self._board = board
        self._rule_engine = rule_engine or RuleEngine()
        self._arbiter = arbiter or RealTimeArbiter()
        self._state = state or GameState()
        self._clock_ms = 0

    # ---- public command boundary --------------------------------------

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
        return MoveResult(True, "ok")

    def wait(self, ms: int) -> None:
        self._clock_ms += ms
        events = self._arbiter.advance_time(self._board, self._clock_ms)
        for event in events:
            if event.captured_kind == config.KING:
                capturer = self._board.piece_by_id(event.piece_id)
                self._state.end_game(winner_color=capturer.color)

    def snapshot(self) -> GameSnapshot:
        pieces = [
            (p.kind, p.color, p.cell.row, p.cell.col, p.state.name)
            for p in self._board.all_pieces()
        ]
        return GameSnapshot(
            board_width=self._board.width,
            board_height=self._board.height,
            pieces=pieces,
            game_over=self._state.game_over,
            winner=self._state.winner,
        )

    # ---- read-only accessors used by BoardPrinter / tests --------------

    @property
    def board(self) -> Board:
        return self._board
