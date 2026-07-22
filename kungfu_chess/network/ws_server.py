"""
WebSocketServer: accepts connections on a plain WebSocket. Step 1 proved
the transport itself can hold multiple concurrent client connections
(pure echo, no game awareness at all). Step 2 (this revision) adds one
thing on top of that: each connection is registered with a
SessionManager and assigned a role (WHITE/BLACK/SPECTATOR) by arrival
order, and a SPECTATOR's MoveRequest/JumpRequest is rejected with an
Error before anything else happens to it.

WHY EVERYTHING THAT ISN'T A REJECTED SPECTATOR MOVE STILL JUST ECHOES:
There is still no GameEngine/EventBus wiring - that is Step 3's job
(see the module docstring this will grow when _echo_handler is replaced
outright). Step 2 only needs to prove role assignment and the
spectator-rejection rule; teaching this handler to actually route
MoveRequest/JumpRequest into a real game would be scope creep ahead of
Step 3, which owns that replacement.

WHY THE SPECTATOR CHECK DECODES THE MESSAGE BUT DOESN'T ROUTE IT
ANYWHERE ON SUCCESS:
protocol.decode() is only consulted here to answer "is this a
MoveRequest/JumpRequest from a spectator" - a session-permission
question SessionManager already has everything it needs to answer
without GameEngine. A message that isn't a rejected spectator move
(including one that fails to decode at all) falls through to the same
echo behavior Step 1 had; Step 3 is what teaches this handler to do
something game-aware with a legitimate player's message.

WHY PORT 0 IS THE DEFAULT FOR TESTS RATHER THAN A FIXED PORT:
Binding to port 0 asks the OS to pick a free ephemeral port, so tests
never collide with each other or with a real server the user may already
have running on the well-known default port.
"""

import asyncio

import websockets

from kungfu_chess.network import protocol
from kungfu_chess.network.session import PlayerRole, SessionManager

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765

_SPECTATOR_REJECTED_TYPES = (protocol.MoveRequest, protocol.JumpRequest)


class WebSocketServer:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self._host = host
        self._port = port
        self._server = None
        self._sessions = SessionManager()

    async def start(self) -> "WebSocketServer":
        self._server = await websockets.serve(self._handle_connection, self._host, self._port)
        return self

    async def _handle_connection(self, websocket) -> None:
        session = self._sessions.register_connection(websocket)
        try:
            async for raw in websocket:
                if session.role is PlayerRole.SPECTATOR and self._is_move_or_jump(raw):
                    await websocket.send(protocol.encode(
                        protocol.Error(reason="spectators_cannot_move")
                    ))
                    continue
                await websocket.send(raw)
        finally:
            self._sessions.unregister_connection(websocket)

    @staticmethod
    def _is_move_or_jump(raw: str) -> bool:
        try:
            return isinstance(protocol.decode(raw), _SPECTATOR_REJECTED_TYPES)
        except (ValueError, KeyError, TypeError, AttributeError):
            return False

    @property
    def port(self) -> int:
        return self._server.sockets[0].getsockname()[1]

    def close(self) -> None:
        if self._server is not None:
            self._server.close()

    async def wait_closed(self) -> None:
        if self._server is not None:
            await self._server.wait_closed()


async def _run_forever(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = await WebSocketServer(host, port).start()
    print(f"KungFuChess WebSocket server listening on ws://{host}:{server.port}")
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(_run_forever())
