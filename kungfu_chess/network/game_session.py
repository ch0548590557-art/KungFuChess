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

WHY connect()/login() ARE SEPARATE (feature/home-screen-basic-login,
Step 3):
connect() just registers a socket (SessionManager.register_connection -
no role yet); login() is the only thing that ever assigns one
(SessionManager.complete_login), called once WebSocketServer's
login_gate.await_login() actually receives a LoginRequest. GameSession
itself does no waiting/timeout logic - that's a transport-timing concern
login_gate.py owns; GameSession only ever answers "given a connection
and a username, who are they now."
"""

from typing import Callable, Optional

from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import MoveCompletedEvent
from kungfu_chess.engine.game_engine import GameEngine
from kungfu_chess.io.board_parser import BoardParser
from kungfu_chess.network import protocol
from kungfu_chess.network.session import PlayerRole, Session, SessionManager

TICK_MS = 50

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
    def __init__(self):
        board = BoardParser().parse(STARTING_POSITION)
        self._sessions = SessionManager()
        self._bus = EventBus()
        self._engine = GameEngine(board, bus=self._bus)
        self._on_move_completed: Optional[Callable[[], None]] = None
        self._bus.subscribe(MoveCompletedEvent, self._handle_move_completed)

    def connect(self, connection) -> Session:
        return self._sessions.register_connection(connection)

    def login(self, connection, username: str) -> Session:
        return self._sessions.complete_login(connection, username)

    def disconnect(self, connection) -> None:
        self._sessions.unregister_connection(connection)

    def on_move_completed(self, callback: Callable[[], None]) -> None:
        self._on_move_completed = callback

    def _handle_move_completed(self, event: MoveCompletedEvent) -> None:
        if self._on_move_completed is not None:
            self._on_move_completed()

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
            self._engine.snapshot(), your_color=session.color,
        )