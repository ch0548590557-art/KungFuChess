import asyncio

from kungfu_chess.model.position import Position
from kungfu_chess.network import protocol
from kungfu_chess.network.client_core import ClientCore
from kungfu_chess.network.ws_server import WebSocketServer


async def _start_server(**kwargs):
    server = await WebSocketServer(port=0, **kwargs).start()
    return server, f"ws://localhost:{server.port}"


async def _stop_server(server):
    server.close()
    await server.wait_closed()


def _client(uri: str, username: str) -> ClientCore:
    """A ClientCore with a username already set, bypassing prepare_login()/
    LoginPrompt entirely - these tests don't care how the username was
    collected, only that connect() sends it (see client_core.py: connect()
    requires self.username to be set, since it sends LoginRequest before
    ever waiting for the welcome)."""
    client = ClientCore(uri)
    client.username = username
    return client


def test_two_clients_learn_their_assigned_colors_on_connect():
    async def scenario():
        server, uri = await _start_server()
        white, black = _client(uri, "alice"), _client(uri, "bob")
        try:
            await white.connect()
            await black.connect()

            assert white.my_color == "w"
            assert black.my_color == "b"
        finally:
            await white.close()
            await black.close()
            await _stop_server(server)

    asyncio.run(scenario())


def test_legal_move_is_broadcast_to_both_clients():
    async def scenario():
        server, uri = await _start_server()
        white, black = _client(uri, "alice"), _client(uri, "bob")
        white_saw_motion = asyncio.Event()
        black_saw_motion = asyncio.Event()

        white.on_state_update(lambda u: white_saw_motion.set() if u.motions else None)
        black.on_state_update(lambda u: black_saw_motion.set() if u.motions else None)

        try:
            await white.connect()
            await black.connect()

            await white.send_move(Position(6, 4), Position(4, 4))

            await asyncio.wait_for(white_saw_motion.wait(), timeout=5)
            await asyncio.wait_for(black_saw_motion.wait(), timeout=5)
        finally:
            await white.close()
            await black.close()
            await _stop_server(server)

    asyncio.run(scenario())


def test_illegal_move_reaches_only_the_sender_as_an_error():
    async def scenario():
        server, uri = await _start_server()
        white, black = _client(uri, "alice"), _client(uri, "bob")
        white_error_seen = asyncio.Event()
        black_errors = []

        white.on_error(lambda error, request: white_error_seen.set())
        black.on_error(lambda error, request: black_errors.append(error))

        try:
            await white.connect()
            await black.connect()

            # A rook has no legal diagonal hop from its own starting cell.
            await white.send_move(Position(7, 0), Position(5, 2))

            await asyncio.wait_for(white_error_seen.wait(), timeout=5)
            assert white.last_error == protocol.Error(
                reason="illegal_piece_move", request_id=white.last_error.request_id,
            )

            await asyncio.sleep(0.2)  # give black a moment to (not) receive anything
            assert black_errors == []
        finally:
            await white.close()
            await black.close()
            await _stop_server(server)

    asyncio.run(scenario())


def test_two_in_flight_requests_are_each_matched_to_their_own_error():
    """The exact scenario request_id exists for: two MoveRequests sent
    back-to-back before either has resolved, both targeting illegal
    destinations - on_error must be able to tell which SentRequest each
    Error belongs to, not just that "something" failed."""
    async def scenario():
        server, uri = await _start_server()
        white = _client(uri, "alice")
        received = []
        done = asyncio.Event()

        def _on_error(error, request):
            received.append((error, request))
            if len(received) == 2:
                done.set()

        white.on_error(_on_error)

        try:
            await white.connect()

            # Neither is a legal rook move from its own starting cell.
            first_id = await white.send_move(Position(7, 0), Position(5, 2))
            second_id = await white.send_move(Position(7, 0), Position(6, 1))

            await asyncio.wait_for(done.wait(), timeout=5)

            by_request_id = {error.request_id: request for error, request in received}

            assert by_request_id[first_id].request_id == first_id
            assert by_request_id[first_id].destination == Position(5, 2)
            assert by_request_id[second_id].request_id == second_id
            assert by_request_id[second_id].destination == Position(6, 1)
        finally:
            await white.close()
            await _stop_server(server)

    asyncio.run(scenario())


def test_dispatcher_still_finds_the_error_under_frequent_broadcast_interleaving():
    async def scenario():
        server, uri = await _start_server(tick_ms=10)  # fast tick to maximize interleaving
        white = _client(uri, "alice")
        error_seen = asyncio.Event()
        white.on_error(lambda error, request: error_seen.set())
        try:
            await white.connect()
            request_id = await white.send_move(Position(7, 0), Position(5, 2))
            await asyncio.wait_for(error_seen.wait(), timeout=5)
            assert white.last_error == protocol.Error(
                reason="illegal_piece_move", request_id=request_id,
            )
        finally:
            await white.close()
            await _stop_server(server)

    asyncio.run(scenario())


def test_second_to_connect_but_first_to_login_gets_white():
    """Proves role assignment follows login order, not the order
    ClientCore.connect() happened to be awaited in - see session.py's
    complete_login()."""
    async def scenario():
        server, uri = await _start_server()
        first_to_connect = _client(uri, "alice")
        second_to_connect = _client(uri, "bob")
        try:
            # Awaiting second_to_connect's connect() to completion before
            # even starting first_to_connect's means it logs in first.
            await second_to_connect.connect()
            await first_to_connect.connect()

            assert second_to_connect.my_color == "w"
            assert first_to_connect.my_color == "b"
        finally:
            await first_to_connect.close()
            await second_to_connect.close()
            await _stop_server(server)

    asyncio.run(scenario())
