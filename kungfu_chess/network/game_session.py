"""
GameSession: the one place that actually understands "what is a
MoveRequest/JumpRequest allowed to do to the real game". It owns the
single Board + GameEngine + EventBus for the whole server process (this
branch supports exactly one game, up to two players - see session.py's
SPECTATOR role for anyone past that), plus the SessionManager built in
Step 2. WebSocketServer (transport) hands every decoded client message
here rather than knowing any of this itself.

WHY THREE DISTINCT Error REASONS (spectators_cannot_move / wrong_color /
GameEngine's own reason) INSTEAD OF ONE GENERIC "rejected":
spectators_cannot_move and wrong_color are *session/identity* questions
("is this connection even allowed to try") that GameEngine has no way to
answer - it has never known about WS connections, colors-of-a-sender, or
spectators. GameEngine's own reasons (illegal_piece_move, outside_board,
game_over, motion_in_progress, empty_source) are *chess/application*
questions it already has a stable vocabulary for (rule_engine.py,
game_engine.py). Collapsing all of these into one string would throw
away information a real client UI needs to show a different message -
"that's not your piece" is not the same problem as "that move is
illegal", and a client can't tell them apart from one shared code.

WHY THE WRONG-COLOR CHECK LIVES HERE AND NOT IN SessionManager:
SessionManager (Step 2) deliberately knows nothing about Board or
pieces (see its own module docstring). Answering "does this session own
the piece at this source cell" needs to read Board - a game-state
question, not a "who is this connection" question - so it belongs in
GameSession, the one class allowed to know about both Session and
GameEngine.

WHY request_move()/request_jump() ARE CALLED DIRECTLY INSTEAD OF
PUBLISHING MoveRequestedEvent/JumpRequestedEvent ON THE BUS:
The local Controller's bus path (input/controller.py) is fire-and-forget
by design - MoveResult is discarded, matching a GUI that finds out what
happened from the next rendered frame. A network client has no
equivalent "next frame" to infer a silent rejection from; it needs an
Error for the specific request that failed. Calling GameEngine directly
gets that return value while GameEngine still publishes
MoveCompletedEvent on success through the same EventBus reference it
was constructed with (game_engine.py's own bus wiring, unchanged) - so
the accept path still flows over the Bus exactly as it does locally,
only the reject path differs.

WHY on_move_completed() IS A PLAIN CALLBACK REGISTRATION INSTEAD OF
GameSession KNOWING ABOUT WEBSOCKETS DIRECTLY:
GameSession has no business knowing what a "connection" is beyond a
hashable key SessionManager already treats generically (see session.py).
The transport (WebSocketServer) is what can actually iterate live
sockets and send bytes; GameSession's only obligation is to say "a move
just completed" the moment MoveCompletedEvent fires, and let whoever
owns the sockets decide what a broadcast means.

WHY GameSession SUBSCRIBES TO GameEndedEvent AND CALLS EloService ITSELF,
RATHER THAN GameEngine CALLING EloService DIRECTLY (feature/auth-sqlite-
elo, Step 5):
GameEngine publishes GameEndedEvent (see its own module docstring) but
has no idea what a "username" is - it only ever deals in board
coordinates and colors. GameSession is the one object that knows both
the chess result (via the same EventBus it already wires GameEngine
into) and the players' identities (via SessionManager.username_for_role,
already used by state_update_for()'s white_username/black_username) - so
it's the only layer that can translate "white just won" into "update
alice's and bob's ratings" at all. elo_service is accepted the same way
auth_service is at the WebSocketServer layer: Optional so the many
existing chess-only GameSession() tests don't need to care, but never
silently swallowed - see _handle_game_ended's own guard comments.

WHY connect()/login() ARE SEPARATE (feature/home-screen-basic-login,
Step 3):
connect() just registers a socket (SessionManager.register_connection -
no role yet); login() is the only thing that ever completes it
(SessionManager.complete_login), called once WebSocketServer's
login_gate.await_login() actually receives a LoginRequest. GameSession
itself does no waiting/timeout logic - that's a transport-timing concern
login_gate.py owns; GameSession only ever answers "given a connection
and a username, who are they now."

WHY GameSession NO LONGER BUILDS ITS OWN SessionManager (feature/
matchmaking-disconnect, Step 2):
Roles used to only ever change at login time, so GameSession owning a
private SessionManager cost nothing - nobody outside GameSession needed
to see or affect it. That stopped being true the moment role assignment
moved to MatchFoundEvent (see session.py's own module docstring):
SessionManager now has to subscribe to that event on a Bus that exists
independently of any one GameSession (a match can be found - and *must*
be answerable - even though this branch still only ever runs a single,
eagerly-created GameSession for the whole process). SessionManager is
therefore built once, above both GameSession and MatchmakingQueue, and
handed in here - GameSession keeps its connect()/login()/disconnect()
facade unchanged, it simply no longer owns what's behind it.

WHY resign_on_disconnect_timeout() LIVES ON GameSession, NOT
SessionManager OR ws_server.py DIRECTLY (feature/matchmaking-disconnect,
Step 4):
Auto-resign needs both "mark this Session RESIGNED" (a SessionManager
fact) and "end the game in the opponent's favor" (a GameEngine fact,
via resign() - see game_engine.py) done together for the one timed-out
player - exactly the same shape as _handle_game_ended above needing both
SessionManager.username_for_role() and the chess result to call
EloService. GameSession is already the one class allowed to know both
Session and GameEngine; ws_server.py only ever needs to know "the
disconnect timer for this session expired", the same way it already
doesn't know anything about SessionManager/GameEngine internals for any
other message it forwards.
"""

from typing import Callable, Optional

from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import GameEndedEvent, MoveCompletedEvent
from kungfu_chess.elo.elo_service import EloService
from kungfu_chess.engine.game_engine import GameEngine
from kungfu_chess.io.board_parser import BoardParser
from kungfu_chess.network import protocol
from kungfu_chess.network.session import PlayerRole, Session, SessionManager, SessionState

TICK_MS = 50


class GameAlreadyEndedError(Exception):
    """Raised by login() when `username` names a reconnect_candidate()
    (see session.py) but the game has already ended by the time the
    login arrives - see login()'s own docstring for the two ways that
    can happen. Deliberately a different reason from
    UsernameAlreadyLoggedInError: nobody is currently online as this
    username (that error would be misleading), the seat itself is just
    gone - there is nothing left to reconnect to."""

    def __init__(self, username: str):
        super().__init__(f"game already ended, no seat to reconnect to: {username}")
        self.username = username
        self.reason = "game_already_ended"

# Mirrors app.py's _run_interactive_window() starting position. Kept as
# its own literal here (rather than importing from app.py) so the
# network package doesn't reach into the interactive-window composition
# root for an unrelated reason - see app.py's own module docstring on
# why build_game()/main() are the only wiring surface it exposes.
STARTING_POSITION = [
    "bR bN bB bQ bK bB bN bR".split(),
    ["bP"] * 8,
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    ["wP"] * 8,
    "wR wN wB wQ wK wB wN wR".split(),
]


class GameSession:
    def __init__(self, sessions: SessionManager, elo_service: Optional[EloService] = None):
        board = BoardParser().parse(STARTING_POSITION)
        self._sessions = sessions
        self._bus = EventBus()
        self._engine = GameEngine(board, bus=self._bus)
        self._elo_service = elo_service
        self._on_move_completed: Optional[Callable[[], None]] = None
        self._bus.subscribe(MoveCompletedEvent, self._handle_move_completed)
        self._bus.subscribe(GameEndedEvent, self._handle_game_ended)

    def connect(self, connection) -> Session:
        return self._sessions.register_connection(connection)

    def login(self, connection, username: str) -> Session:
        """A LoginRequest/RegisterRequest just resolved to `username` on
        `connection` - the normal login path, unchanged for a brand-new
        or currently-ACTIVE username (see reconnect_candidate()'s own
        docstring on why those fall straight through to
        complete_login()). When `username` names a non-ACTIVE WHITE/BLACK
        seat instead (feature/matchmaking-disconnect, Step 5), this is a
        reconnect attempt - handled here rather than in SessionManager
        because completing it safely needs a fact only this class can
        see: is the game already over. Several different, independently
        real ways it can be by the time this runs - all must reject
        cleanly rather than hand back a seat in a finished game:
          1. The seat is RESIGNED - its own disconnect timer already
             expired (Step 4) - which, by construction, already means
             game_over is True (see reconnect_candidate()'s own note).
          2. The seat is DISCONNECTED, but the *opponent's* disconnect
             timer already expired and ended the game first - this
             player was never told, since they were offline.
          3. The genuine race this branch's Step 4 design discussion
             already flagged: *this* player's own disconnect timer
             expires in the brief asyncio.wait_for() cancellation gap
             around the same moment this reconnect arrives - see
             resign_on_disconnect_timeout()'s own guard for the other
             half of this (the timer noticing a reconnect beat it, not
             this method noticing a resign beat it).
        Checking self._engine.game_over here, synchronously and with
        nothing awaited before reconnect() actually reattaches the
        connection, is what makes case 3 safe: nothing else can run
        between this check and reconnect() to invalidate it (see
        session.py's own note on why no Lock is needed for the same
        reason)."""
        candidate = self._sessions.reconnect_candidate(username)
        if candidate is not None:
            if self._engine.game_over:
                raise GameAlreadyEndedError(username)
            return self._sessions.reconnect(connection, candidate)
        return self._sessions.complete_login(connection, username)

    def resign_on_disconnect_timeout(self, session: Session) -> None:
        """Called by ws_server.py's disconnect-timer task (Step 3) the
        moment ReconnectTimeout actually fires for `session` - guard 7b
        (see session.py's unregister_connection()) guarantees `session`
        is still the same WHITE/BLACK player whose countdown started, so
        session.color is never None here.

        WHY THIS CHECKS session.state BEFORE DOING ANYTHING (feature/
        matchmaking-disconnect, Step 5):
        ReconnectTimeout firing does not, on its own, guarantee no
        reconnect happened - asyncio.wait_for()'s internal cancel-then-
        raise sequence takes an extra event-loop tick (verified by
        tracing it, not assumed - see this branch's Step 5 design notes),
        so login()'s reconnect() can run and flip `session` back to
        ACTIVE in the gap between this timer's timeout being decided and
        this handler actually running. A stale ReconnectTimeout must not
        resign a player who is, by the time this line runs, already back
        - checking state here (not just relying on GameEngine.resign()'s
        own game_over guard, which only catches the *other* color already
        having ended the game, see Step 4) is what catches that.

        Once past that guard, marks the session RESIGNED (SessionManager.
        mark_resigned - the first producer of that state, Step 4) and
        hands off to GameEngine.resign(), which already owns "end the
        game in the opponent's favor" and is what makes a second,
        near-simultaneous call - the other color's own timer expiring a
        moment later - a safe no-op rather than a second GameEndedEvent
        (see resign()'s own docstring)."""
        if session.state is not SessionState.DISCONNECTED:
            return  # reconnected in the gap - see the docstring above
        self._sessions.mark_resigned(session)
        self._engine.resign(session.color, reason="opponent_disconnected")

    def disconnect(self, connection) -> Optional[Session]:
        """Returns the Session if - and only if - this disconnect just
        started a disconnect countdown for an active WHITE/BLACK player
        (see SessionManager.unregister_connection() - the return value
        already embeds guard 7b, so ws_server.py doesn't need its own
        "is a timer already running" check before starting one)."""
        return self._sessions.unregister_connection(connection)

    def on_move_completed(self, callback: Callable[[], None]) -> None:
        self._on_move_completed = callback

    def _handle_move_completed(self, event: MoveCompletedEvent) -> None:
        if self._on_move_completed is not None:
            self._on_move_completed()

    def _handle_game_ended(self, event: GameEndedEvent) -> None:
        if self._elo_service is None:
            return
        white_username = self._sessions.username_for_role(PlayerRole.WHITE)
        black_username = self._sessions.username_for_role(PlayerRole.BLACK)
        if white_username is None or black_username is None:
            # Nobody ever logged in as one of the colors (e.g. this
            # GameSession is only used in a chess-logic test with no real
            # players) - there is nobody to rate.
            return
        self._elo_service.record_game_result(white_username, black_username, event.winner_color)

    def handle_message(self, session: Session, raw: str) -> Optional[protocol.Error]:
        try:
            message = protocol.decode(raw)
        except protocol.UnknownMessageType:
            return protocol.Error(reason="unknown_message_type")
        except (ValueError, KeyError, TypeError, AttributeError):
            return protocol.Error(reason="malformed_message")

        if isinstance(message, protocol.MoveRequest):
            return self._handle_move(session, message)
        if isinstance(message, protocol.JumpRequest):
            return self._handle_jump(session, message)
        # Syntactically valid and a recognized type, but not one a client
        # is ever supposed to send (GameStateUpdate/Error are server->
        # client only) - no request_id to echo, since this isn't even a
        # request type.
        return protocol.Error(reason="unknown_message_type")

    def _handle_move(self, session: Session, message: protocol.MoveRequest) -> Optional[protocol.Error]:
        reason = self._check_permission(session, message.source)
        if reason is None:
            result = self._engine.request_move(message.source, message.destination)
            if not result.is_accepted:
                reason = result.reason
        if reason is None:
            return None
        return protocol.Error(reason=reason, request_id=message.request_id)

    def _handle_jump(self, session: Session, message: protocol.JumpRequest) -> Optional[protocol.Error]:
        reason = self._check_permission(session, message.source)
        if reason is None:
            result = self._engine.request_jump(message.source)
            if not result.is_accepted:
                reason = result.reason
        if reason is None:
            return None
        return protocol.Error(reason=reason, request_id=message.request_id)

    def _check_permission(self, session: Session, source) -> Optional[str]:
        """Returns a rejection reason string, or None if the sender is
        allowed to act on `source` (existence/color of the piece there
        is still GameEngine's own call - a permission check only answers
        who this session is, never whether the eventual move is legal)."""
        if session.role is PlayerRole.SPECTATOR:
            return "spectators_cannot_move"
        piece = self._engine.board.piece_at(source)
        if piece is not None and piece.color != session.color:
            return "wrong_color"
        return None

    def tick(self, ms: int) -> None:
        self._engine.wait(ms)

    def state_update_for(self, session: Session) -> protocol.GameStateUpdate:
        return protocol.GameStateUpdate.from_snapshot(
            self._engine.snapshot(),
            your_color=session.color,
            white_username=self._sessions.username_for_role(PlayerRole.WHITE),
            black_username=self._sessions.username_for_role(PlayerRole.BLACK),
            remaining_seconds=self._sessions.remaining_disconnect_seconds(),
        )