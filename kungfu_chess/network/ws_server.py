"""
WebSocketServer: Step 1 of the single-process transport - accept
connections on a plain WebSocket and echo back whatever each client
sends. There is no game wiring yet (no EventBus, no GameEngine); this
class only has to prove the transport itself can hold multiple
concurrent client connections on localhost before any protocol or game
logic is layered on top of it.

WHY ECHO INSTEAD OF A NO-OP HANDLER:
A handler that does nothing would still prove "the server accepts
connections", but not "each connection can independently send and
receive" - echo is the smallest behavior that exercises both directions
of the socket per client, which is what the concurrent-clients test
needs to observe.

WHY PORT 0 IS THE DEFAULT FOR TESTS RATHER THAN A FIXED PORT:
Binding to port 0 asks the OS to pick a free ephemeral port, so tests
never collide with each other or with a real server the user may already
have running on the well-known default port.
"""

import asyncio

import websockets

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765


async def _echo_handler(websocket) -> None:
    async for message in websocket:
        await websocket.send(message)


class WebSocketServer:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self._host = host
        self._port = port
        self._server = None

    async def start(self) -> "WebSocketServer":
        self._server = await websockets.serve(_echo_handler, self._host, self._port)
        return self

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
