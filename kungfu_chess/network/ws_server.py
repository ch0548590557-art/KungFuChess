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

WHY THE SERVER SENDS ONE GameStateUpdate IMMEDIATELY ON CONNECT:
So a client learns its assigned color (GameStateUpdate.your_color)
right away instead of waiting up to one tick interval for the first
scheduled broadcast.

WHY PORT 0 IS THE DEFAULT FOR TESTS RATHER THAN A FIXED PORT:
Binding to port 0 asks the OS to pick a free ephemeral port, so tests
never collide with each other or with a real server the user may already
have running on the well-known default port.
"""

import asyncio

import websockets

from kungfu_chess.network import protocol
from kungfu_chess.network.game_session import GameSession, TICK_MS

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765


class WebSocketServer:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 tick_ms: int = TICK_MS):
        self._host = host
        self._port = port
        self._tick_ms = tick_ms
        self._server = None
        self._tick_task = None
        self._game = GameSession()
        self._game.on_move_completed(self._schedule_broadcast)
        self._connections = {}  # websocket -> Session

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
        session = self._game.connect(websocket)
        self._connections[websocket] = session
        try:
            await websocket.send(protocol.encode(self._game.state_update_for(session)))
            async for raw in websocket:
                reply = self._game.handle_message(session, raw)
                if reply is not None:
                    await websocket.send(protocol.encode(reply))
        finally:
            self._game.disconnect(websocket)
            del self._connections[websocket]

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