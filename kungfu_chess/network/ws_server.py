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

WHY EVERY CONNECT/DISCONNECT IS PRINTED:
Discovered while manually playtesting (2026-07-22): a human juggling
several terminal windows has no other way to tell how many clients are
actually connected right now, or which role a given terminal got - a
stray disconnected client silently frees its color, and the next
connection quietly claims it (see session.py), which looks identical to
"the server assigned the wrong role" from the outside. This line is the
cheapest way to make that state observable without building a real
admin/monitoring surface.
"""

import asyncio

import websockets

from kungfu_chess.network import protocol
from kungfu_chess.network.game_session import GameSession, TICK_MS
from kungfu_chess.network.login_gate import (
    DEFAULT_LOGIN_TIMEOUT_SECONDS,
    LoginFailed,
    LoginTimeout,
    await_login,
)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765


class WebSocketServer:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 tick_ms: int = TICK_MS,
                 login_timeout_seconds: float = DEFAULT_LOGIN_TIMEOUT_SECONDS):
        self._host = host
        self._port = port
        self._tick_ms = tick_ms
        self._login_timeout_seconds = login_timeout_seconds
        self._server = None
        self._tick_task = None
        self._game = GameSession()
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
                login = await await_login(websocket, self._login_timeout_seconds)
            except LoginTimeout:
                print(f"[login-timeout] connections={len(self._connections)}")
                await websocket.send(protocol.encode(protocol.Error(reason="login_timeout")))
                return
            except LoginFailed as exc:
                print(f"[login-failed] reason={exc.reason} connections={len(self._connections)}")
                await websocket.send(protocol.encode(protocol.Error(reason=exc.reason)))
                return

            session = self._game.login(websocket, login.username)
            self._connections[websocket] = session
            print(f"[connect] username={session.username} role={session.role.name} "
                  f"color={session.color} connections={len(self._connections)}")

            await websocket.send(protocol.encode(self._game.state_update_for(session)))
            async for raw in websocket:
                reply = self._game.handle_message(session, raw)
                if reply is not None:
                    await websocket.send(protocol.encode(reply))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._game.disconnect(websocket)
            logged_in_session = self._connections.pop(websocket, None)
            if logged_in_session is not None:
                print(f"[disconnect] username={logged_in_session.username} "
                      f"role={logged_in_session.role.name} color={logged_in_session.color} "
                      f"connections={len(self._connections)}")

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
    server = await WebSocketServer(host, port).start()
    print(f"KungFuChess WebSocket server listening on ws://{host}:{server.port}")
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(_run_forever())