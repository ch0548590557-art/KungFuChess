"""
WebSocketServer: the real game-aware transport (Step 3 replaces Steps
1/2's plain-echo path entirely - there is no echo fallback left). It
decodes nothing itself and knows nothing about chess: every client
message is handed to GameSession.handle_message(), and every broadcast
is built by GameSession.state_update_for(). Its only two jobs are (1)
own the actual sockets and (2) decide *when* to broadcast.

TWO THINGS DRIVE A BROADCAST TO EVERY CONNECTED CLIENT:
1. An accepted MoveRequest/JumpRequest - GameSession's MoveCompletedEvent
   subscription (see game_session.py) calls back into
   _schedule_broadcast() synchronously, from inside the same coroutine
   that received the client's message, so acceptance is reflected
   immediately rather than waiting for the next tick.
2. A fixed ~20Hz tick loop that advances GameEngine's simulated clock
   (engine.wait()) so in-flight motions actually arrive - captures,
   promotions, and game-over all happen at *arrival* time (Section 10),
   which nothing but a running clock can ever reach. Without this loop,
   an accepted move would sit "in flight" forever (see this branch's
   Step 3 architecture note on why GameEngine.wait() must be driven by
   something in a headless server, unlike the local GUI's per-frame
   GameWindow.run() -> engine.wait(delta_ms)).

WHY THE TICK LOOP BROADCASTS UNCONDITIONALLY EVERY TICK RATHER THAN ONLY
ON CHANGE:
Detecting "did anything change" would mean either diffing snapshots or
teaching GameEngine to report it - both add complexity this
single-process, two-client branch doesn't need yet. An unconditional
~20Hz broadcast is the smallest thing that keeps every connected
client's board eventually consistent with the server's.

WHY THE SERVER SENDS ONE GameStateUpdate IMMEDIATELY ON LOGIN:
So a client learns its assigned color (GameStateUpdate.your_color)
right away instead of waiting up to one tick interval for the first
scheduled broadcast. As of feature/home-screen-basic-login (Step 3),
this happens after a successful login, not on raw connect - see below.

WHY WebSocketServer REQUIRES AuthService/EloService CONSTRUCTOR ARGUMENTS
WITH NO DEFAULT (auth_service: feature/auth-sqlite-elo Step 4; elo_service:
Step 5):
login_gate.await_login() checks every RegisterRequest/LoginRequest
against a real AuthService (auth/auth_service.py) instead of accepting
any username, and GameSession updates ratings through a real EloService
(elo/elo_service.py) when a game ends - WebSocketServer is the
transport-layer owner of both dependencies (GameSession itself stays
auth/rating-agnostic beyond the one EloService reference it's handed,
see game_session.py), so it must be handed both explicitly rather than
silently constructing its own against some guessed default DB path.
_run_forever() is the one call site that builds real ones (sharing a
single UserRepository, so a login and a rating update touch the same
users table) for actual server runs; every test constructs its own
(usually in-memory) instances.

WHY A CONNECTION MUST LOG IN (LoginRequest) BEFORE ANYTHING ELSE
HAPPENS, AND WHY IT HAS A TIMEOUT (feature/home-screen-basic-login,
Step 3):
Role assignment (session.py) is now keyed on *login* order, not raw
TCP-accept order, so a connection that hasn't logged in yet must not be
treated as a real player OR a spectator - it isn't added to
self._connections (and therefore never appears in a broadcast, never
gets the welcome GameStateUpdate) until login_gate.await_login()
actually returns a LoginRequest. A client that never logs in would
otherwise hold a socket open forever with no way for the server to ever
reclaim it, so await_login() is bounded by login_timeout_seconds; on
timeout or a malformed/wrong-type first message, the server sends a
single Error and closes the connection (returning from
_handle_connection ends the coroutine, which the websockets library
treats as "close this connection").

WHY ClientCore MUST SEND LoginRequest BEFORE WAITING FOR THE WELCOME:
This is the flip side of the same design - since the server won't
send anything until login arrives, and ClientCore.connect() blocks
until the first GameStateUpdate arrives, sending login is what unblocks
it. Getting this order backwards on the client side (wait for welcome,
then send login) would deadlock every single connection: see
client_core.py's own note and this branch's explicit "client that never
logs in" test proving the *server* side degrades to a clean timeout
rather than a silent hang.

WHY PORT 0 IS THE DEFAULT FOR TESTS RATHER THAN A FIXED PORT:
Binding to port 0 asks the OS to pick a free ephemeral port, so tests
never collide with each other or with a real server the user may already
have running on the well-known default port.

WHY WebSocketServer NOW ALSO OWNS A SHARED EventBus, SessionManager, AND
MatchmakingQueue (feature/matchmaking-disconnect, Step 2):
GameSession used to build its own private SessionManager, since roles
never changed except at login time (see game_session.py's own note on
this). Role assignment now happens via MatchFoundEvent, published by
MatchmakingQueue and consumed by SessionManager - both need to share one
Bus that outlives any single GameSession, since this branch's compromise
architecture still runs exactly one GameSession, built once, for the
whole process (see session.py's module docstring on why a spectator
mid-game can't queue for a "next" one yet). WebSocketServer is the
existing composition root (already the one place AuthService/EloService
come together), so it's also where this Bus, SessionManager, and
MatchmakingQueue are built, with SessionManager then handed into
GameSession rather than GameSession building its own.

WHY WebSocketServer NOW REQUIRES A UserRepository CONSTRUCTOR ARGUMENT
(feature/matchmaking-disconnect, Step 2):
A PlayRequest's rating must come from the server, never the client (see
session.py's begin_queueing() docstring and MatchmakingQueue.enqueue()'s
own signature) - looked up fresh at PlayRequest time, not cached from
login, since login_gate.await_login() only ever returns a bare username
(see its own docstring), never the full User row. AuthService's
interface is deliberately narrow ("is this username+password real" -
see auth_service.py) and has no rating-lookup method, so this needs a
direct UserRepository reference, the same one already shared between
auth_service and elo_service in _run_forever().

WHY PlayRequest/CancelPlayRequest ARE HANDLED HERE INSTEAD OF INSIDE
GameSession.handle_message() (Step 2):
MatchmakingQueue.enqueue() is async and can legitimately block for up to
its whole timeout window (default 60s) waiting for an opponent -
handle_message() is a plain synchronous call made from inside this
connection's own message loop, and awaiting enqueue() there would freeze
that connection's ability to process anything else (including its own
CancelPlayRequest) for as long as it's queued. WebSocketServer already
owns the only thing that can run this concurrently with the rest of a
connection's traffic - a background task, the same pattern
_schedule_broadcast() already uses for a different reason. GameSession
stays synchronous and chess-only; every message is still decoded exactly
once (this module decodes first and forwards the original `raw` to
GameSession unchanged when it isn't a PlayRequest/CancelPlayRequest, so
GameSession's own malformed/unknown-type handling is untouched).

WHY EVERY CONNECT/DISCONNECT IS PRINTED:
Discovered while manually playtesting (2026-07-22): a human juggling
several terminal windows has no other way to tell how many clients are
actually connected right now, or which role a given terminal got - a
stray disconnected spectator vanishes and a new login can quietly claim
a freed color, which looks identical to "the server assigned the wrong
role" from the outside (an *active* player disconnecting no longer frees
anything immediately - see session.py's unregister_connection(), Step
3). This line is the cheapest way to make that state observable without
building a real admin/monitoring surface.

WHY DISCONNECT-TIMER TASKS ARE SPAWNED HERE, FROM _handle_connection()'s
OWN finally BLOCK, RATHER THAN INSIDE SessionManager (feature/
matchmaking-disconnect, Step 3):
SessionManager.unregister_connection() stays synchronous and
asyncio-ignorant, matching every other method on it - it only ever
answers "what changed" (see its own docstring: it returns the Session
exactly when a *new* countdown needs to start, embedding guard 7b so the
caller never has to check separately). Actually *waiting* 20 seconds is
a transport-timing concern with nothing session-specific about it - the
same reasoning login_gate.py's await_login() and this module's own
_handle_play_request() already lean on - so it's spawned here as a
background task (asyncio.ensure_future(), same pattern as
_schedule_broadcast()/_handle_play_request()), detached from the
now-finished connection coroutine, calling straight into
disconnect_timer.py's await_reconnect_or_timeout().
"""

import asyncio
from typing import Optional

import websockets

from kungfu_chess.auth.auth_service import AuthService, SqliteAuthService
from kungfu_chess.auth.sqlite_user_repository import SqliteUserRepository
from kungfu_chess.auth.user_repository import UserRepository
from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.elo.elo_service import EloService
from kungfu_chess.matchmaking.matchmaking_queue import MatchmakingQueue, MatchmakingTimeout
from kungfu_chess.network import protocol
from kungfu_chess.network.disconnect_timer import (
    DEFAULT_DISCONNECT_TIMEOUT_SECONDS,
    ReconnectTimeout,
    await_reconnect_or_timeout,
)
from kungfu_chess.network.game_session import GameAlreadyEndedError, GameSession, TICK_MS
from kungfu_chess.network.login_gate import (
    DEFAULT_LOGIN_TIMEOUT_SECONDS,
    LoginFailed,
    LoginTimeout,
    await_login,
)
from kungfu_chess.network.session import PlayerRole, Session, SessionManager, UsernameAlreadyLoggedInError

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765
DEFAULT_USER_DB_PATH = "kungfuchess_users.sqlite3"


def _role_name(role: Optional[PlayerRole]) -> str:
    """role is None for a logged-in connection with no active game yet
    (see session.py) - a state that didn't used to exist right after
    login, so the old `session.role.name` here would now raise on it."""
    return role.name if role is not None else "NONE"


def _try_decode(raw: str) -> Optional[protocol.Message]:
    """A tolerant peek used only to recognize PlayRequest/CancelPlayRequest
    before GameSession ever sees the message (see the module docstring) -
    any decode failure here is not this function's problem to report;
    the unmodified `raw` still gets passed to GameSession.handle_message(),
    which already owns malformed/unknown-type error reporting."""
    try:
        return protocol.decode(raw)
    except (protocol.UnknownMessageType, ValueError, KeyError, TypeError, AttributeError):
        return None


class WebSocketServer:
    def __init__(self, auth_service: AuthService, elo_service: EloService,
                 user_repository: UserRepository,
                 host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 tick_ms: int = TICK_MS,
                 login_timeout_seconds: float = DEFAULT_LOGIN_TIMEOUT_SECONDS,
                 disconnect_timeout_seconds: float = DEFAULT_DISCONNECT_TIMEOUT_SECONDS):
        self._auth_service = auth_service
        self._user_repository = user_repository
        self._host = host
        self._port = port
        self._tick_ms = tick_ms
        self._login_timeout_seconds = login_timeout_seconds
        self._disconnect_timeout_seconds = disconnect_timeout_seconds
        self._server = None
        self._tick_task = None
        match_bus = EventBus()
        self._sessions = SessionManager(match_bus, disconnect_timeout_seconds)
        self._matchmaking = MatchmakingQueue(match_bus)
        self._game = GameSession(self._sessions, elo_service)
        self._game.on_move_completed(self._schedule_broadcast)
        self._connections = {}  # websocket -> Session, logged-in connections only

    async def start(self) -> "WebSocketServer":
        self._server = await websockets.serve(self._handle_connection, self._host, self._port)
        self._tick_task = asyncio.ensure_future(self._tick_loop())
        return self

    @property
    def port(self) -> int:
        return self._server.sockets[0].getsockname()[1]

    def close(self) -> None:
        if self._tick_task is not None:
            self._tick_task.cancel()
        if self._server is not None:
            self._server.close()

    async def wait_closed(self) -> None:
        if self._server is not None:
            await self._server.wait_closed()

    async def _handle_connection(self, websocket) -> None:
        self._game.connect(websocket)  # pending - no role, not in self._connections yet
        try:
            try:
                username = await await_login(websocket, self._auth_service, self._login_timeout_seconds)
            except LoginTimeout:
                print(f"[login-timeout] connections={len(self._connections)}")
                await websocket.send(protocol.encode(protocol.Error(reason="login_timeout")))
                return
            except LoginFailed as exc:
                print(f"[login-failed] reason={exc.reason} connections={len(self._connections)}")
                await websocket.send(protocol.encode(protocol.Error(reason=exc.reason)))
                return

            try:
                session = self._game.login(websocket, username)
            except (UsernameAlreadyLoggedInError, GameAlreadyEndedError) as exc:
                print(f"[login-failed] reason={exc.reason} connections={len(self._connections)}")
                await websocket.send(protocol.encode(protocol.Error(reason=exc.reason)))
                return

            self._connections[websocket] = session
            print(f"[connect] username={session.username} role={_role_name(session.role)} "
                  f"color={session.color} connections={len(self._connections)}")

            await websocket.send(protocol.encode(self._game.state_update_for(session)))
            async for raw in websocket:
                message = _try_decode(raw)
                if isinstance(message, protocol.PlayRequest):
                    asyncio.ensure_future(self._handle_play_request(websocket, session))
                    continue
                if isinstance(message, protocol.CancelPlayRequest):
                    self._handle_cancel_play_request(session)
                    continue
                reply = self._game.handle_message(session, raw)
                if reply is not None:
                    await websocket.send(protocol.encode(reply))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            disconnected_session = self._game.disconnect(websocket)
            logged_in_session = self._connections.pop(websocket, None)
            if logged_in_session is not None:
                print(f"[disconnect] username={logged_in_session.username} "
                      f"role={_role_name(logged_in_session.role)} color={logged_in_session.color} "
                      f"connections={len(self._connections)}")
            if disconnected_session is not None:
                # Only non-None the *first* time an active player's socket
                # closes (guard 7b already applied inside
                # SessionManager.unregister_connection()) - a flaky
                # connection that drops twice never starts a second timer.
                asyncio.ensure_future(self._handle_disconnect_timer(disconnected_session))

    async def _handle_disconnect_timer(self, session: Session) -> None:
        """Runs as a background task, detached from this connection's own
        (now-finished) lifecycle - same reason _handle_play_request is one
        (see its own docstring): a bounded wait has no business blocking
        anything else. On timeout, hands off to GameSession.resign_on_
        disconnect_timeout() (feature/matchmaking-disconnect, Step 4) -
        no explicit broadcast here, since the next ~20Hz tick (at most
        self._tick_ms away) already picks up the now game_over state the
        same way it already does for a king-capture ending (decision 8 -
        see session.py's remaining_disconnect_seconds() docstring). See
        disconnect_timer.py's own module docstring on why this still
        waits on session.reconnected rather than a bare asyncio.sleep()."""
        try:
            await await_reconnect_or_timeout(session.reconnected, self._disconnect_timeout_seconds)
        except ReconnectTimeout:
            print(f"[disconnect-timeout] username={session.username} role={_role_name(session.role)} "
                  f"- auto-resigning")
            self._game.resign_on_disconnect_timeout(session)

    async def _handle_play_request(self, websocket, session) -> None:
        """Runs as a background task (see the module docstring) so
        MatchmakingQueue.enqueue() blocking for up to its whole timeout
        window never freezes this connection's own message loop -
        CancelPlayRequest for the same connection can still be processed
        while this is in flight."""
        username = session.username
        reason = self._sessions.begin_queueing(username)
        if reason is not None:
            await self._safe_send(websocket, protocol.Error(reason=reason))
            return

        user = self._user_repository.get_by_username(username)
        try:
            await self._matchmaking.enqueue(username, user.rating)
        except MatchmakingTimeout:
            await self._safe_send(websocket, protocol.Error(reason="matchmaking_timeout"))
        finally:
            self._sessions.end_queueing(username)

    def _handle_cancel_play_request(self, session) -> None:
        """Idempotent by construction - MatchmakingQueue.cancel() and
        SessionManager.end_queueing() are both safe no-ops if `session`
        isn't actually queued (see their own docstrings), so there is
        nothing to check before calling either."""
        self._matchmaking.cancel(session.username)
        self._sessions.end_queueing(session.username)

    async def _safe_send(self, websocket, message) -> None:
        """PlayRequest handling runs detached from the connection's own
        try/except ConnectionClosed (see _handle_play_request's docstring
        on why it's a background task) - it needs its own guard against
        sending to a socket that died while this was waiting on
        MatchmakingQueue."""
        try:
            await websocket.send(protocol.encode(message))
        except websockets.exceptions.ConnectionClosed:
            pass

    def _schedule_broadcast(self) -> None:
        """GameSession's MoveCompletedEvent subscriber calls this
        synchronously (EventBus.publish() is sync) from inside
        engine.request_move()/request_jump(), itself called synchronously
        from inside _handle_connection()'s message loop - so a broadcast
        can only be *scheduled* here as a new task, never awaited
        directly (this function isn't async; blocking the publisher
        would make GameEngine implicitly async, which it must never
        become)."""
        asyncio.ensure_future(self._broadcast())

    async def _tick_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._tick_ms / 1000)
                self._game.tick(self._tick_ms)
                await self._broadcast()
        except asyncio.CancelledError:
            pass

    async def _broadcast(self) -> None:
        if not self._connections:
            return
        await asyncio.gather(
            *(ws.send(protocol.encode(self._game.state_update_for(session)))
              for ws, session in self._connections.items()),
            return_exceptions=True,
        )


async def _run_forever(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    user_repository = SqliteUserRepository(DEFAULT_USER_DB_PATH)
    auth_service = SqliteAuthService(user_repository)
    elo_service = EloService(user_repository)
    server = await WebSocketServer(auth_service, elo_service, user_repository, host, port).start()
    print(f"KungFuChess WebSocket server listening on ws://{host}:{server.port}")
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(_run_forever())