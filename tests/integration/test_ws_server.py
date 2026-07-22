import asyncio

import websockets

from kungfu_chess.network.ws_server import WebSocketServer


def test_two_clients_connect_concurrently_and_are_echoed_independently():
    async def scenario():
        server = await WebSocketServer(port=0).start()
        uri = f"ws://localhost:{server.port}"
        try:
            async with websockets.connect(uri) as client_a, \
                    websockets.connect(uri) as client_b:
                # Both sockets are open at once - interleave sends so a
                # broken second connection (or a server that only serves
                # one client at a time) would show up as a hang or a
                # wrong echo here.
                await client_a.send("hello from A")
                await client_b.send("hello from B")

                echo_a = await client_a.recv()
                echo_b = await client_b.recv()

                assert echo_a == "hello from A"
                assert echo_b == "hello from B"

                # Round-trip again on both to prove neither connection
                # was a one-shot fluke.
                await client_b.send("second message from B")
                assert await client_b.recv() == "second message from B"

                await client_a.send("second message from A")
                assert await client_a.recv() == "second message from A"
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_server_reports_its_bound_port_when_started_on_port_zero():
    async def scenario():
        server = await WebSocketServer(port=0).start()
        try:
            assert server.port != 0
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())
