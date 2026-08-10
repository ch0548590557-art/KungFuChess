import asyncio

from kungfu_chess.auth.auth_service import SqliteAuthService
from kungfu_chess.auth.sqlite_user_repository import SqliteUserRepository
from kungfu_chess.elo.elo_service import EloService
from kungfu_chess.model.position import Position
from kungfu_chess.network import protocol
from kungfu_chess.network.client_core import ClientCore
from kungfu_chess.network.ws_server import WebSocketServer


async def _start_server(**kwargs):
    # A fresh in-memory UserRepository per server, shared by auth_service,
    # elo_service, and (feature/matchmaking-disconnect, Step 2) matchmaking
    # rating lookups - see test_ws_server.py's _start() for why.
    user_repository = SqliteUserRepository(":memory:")
    auth_service = SqliteAuthService(user_repository)
    elo_service = EloService(user_repository)
    server = await WebSocketServer(auth_service, elo_service, user_repository, port=0, **kwargs).start()
    return server, f"ws://localhost:{server.port}"


async def _stop_server(server):
    server.close()
    await server.wait_closed()


def _client(uri: str, username: str, password: str = "hunter2") -> ClientCore:
    """A ClientCore with credentials already set, bypassing prepare_login()/
    LoginPrompt entirely - these tests don't care how the credentials were
    collected, only that connect() sends them (see client_core.py: connect()
    requires self.username/self._password to be set, since it sends
    RegisterRequest/LoginRequest before ever waiting for the welcome).
    Defaults to the "register" action - every test starts a fresh
    in-memory user DB via _start_server(), so every username used here is
    always new."""
    client = ClientCore(uri)
    client.username = username
    client._password = password
    client._login_action = "register"
    return client


async def _match(first: ClientCore, second: ClientCore) -> None:
    """Sends PlayRequest on both (already-connected) clients and waits
    for each to see itself assigned a color - the feature/matchmaking-
    disconnect Step 2 replacement for what connect() used to do by
    itself (see session.py: login no longer assigns a role). `first`
    gets a head start so it's guaranteed to end up White (decision 3:
    whoever waited longer becomes White) - a real network round trip
    has no other way to guarantee queue order deterministically."""
    await first.send_play_request()
    await asyncio.sleep(0.1)
    await second.send_play_request()

    async def _wait_for_color(client: ClientCore) -> None:
        while client.my_color is None:
            await asyncio.sleep(0.02)

    await asyncio.wait_for(_wait_for_color(first), timeout=5)
    await asyncio.wait_for(_wait_for_color(second), timeout=5)


def test_two_clients_get_matched_and_assigned_colors_via_play_request():
    async def scenario():
        server, uri = await _start_server()
        white, black = _client(uri, "alice"), _client(uri, "bob")
        try:
            await white.connect()
            await black.connect()
            assert white.my_color is None  # login alone assigns no role
            assert black.my_color is None

            await _match(white, black)

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
            await _match(white, black)

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
            await _match(white, black)

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
        white, black = _client(uri, "alice"), _client(uri, "bob")
        received = []
        done = asyncio.Event()

        def _on_error(error, request):
            received.append((error, request))
            if len(received) == 2:
                done.set()

        white.on_error(_on_error)

        try:
            await white.connect()
            await black.connect()
            await _match(white, black)  # white needs a real role to send moves at all

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
            await black.close()
            await _stop_server(server)

    asyncio.run(scenario())


def test_dispatcher_still_finds_the_error_under_frequent_broadcast_interleaving():
    async def scenario():
        server, uri = await _start_server(tick_ms=10)  # fast tick to maximize interleaving
        white, black = _client(uri, "alice"), _client(uri, "bob")
        error_seen = asyncio.Event()
        white.on_error(lambda error, request: error_seen.set())
        try:
            await white.connect()
            await black.connect()
            await _match(white, black)

            request_id = await white.send_move(Position(7, 0), Position(5, 2))
            await asyncio.wait_for(error_seen.wait(), timeout=5)
            assert white.last_error == protocol.Error(
                reason="illegal_piece_move", request_id=request_id,
            )
        finally:
            await white.close()
            await black.close()
            await _stop_server(server)

    asyncio.run(scenario())


def test_play_request_order_determines_white_not_connect_order():
    """Role assignment no longer follows connect/login order at all
    (feature/matchmaking-disconnect, Step 2 - see session.py) - only
    queue-wait order does. Proves that even though `first_to_connect`
    connects (and logs in) first, if it sends PlayRequest *after* the
    other client, it ends up Black."""
    async def scenario():
        server, uri = await _start_server()
        first_to_connect = _client(uri, "alice")
        second_to_connect = _client(uri, "bob")
        try:
            await first_to_connect.connect()
            await second_to_connect.connect()
            assert first_to_connect.my_color is None
            assert second_to_connect.my_color is None

            # second_to_connect queues first this time.
            await _match(second_to_connect, first_to_connect)

            assert second_to_connect.my_color == "w"
            assert first_to_connect.my_color == "b"
        finally:
            await first_to_connect.close()
            await second_to_connect.close()
            await _stop_server(server)

    asyncio.run(scenario())