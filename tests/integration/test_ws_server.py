import asyncio

import websockets

from kungfu_chess.model.position import Position
from kungfu_chess.network import protocol
from kungfu_chess.network.ws_server import WebSocketServer


async def _start(**kwargs):
    server = await WebSocketServer(port=0, **kwargs).start()
    return server, f"ws://localhost:{server.port}"


async def _stop(server):
    server.close()
    await server.wait_closed()


async def _welcome(connection) -> protocol.GameStateUpdate:
    """Every connection's first message is a personalized GameStateUpdate
    (see ws_server.py: sent immediately on connect so a client learns its
    color without waiting for the first tick)."""
    return protocol.decode(await connection.recv())


async def _recv_until(connection, predicate, timeout: float = 5.0):
    """Read messages off `connection` until one satisfies `predicate`,
    skipping any that don't.

    WHY THIS EXISTS INSTEAD OF JUST `protocol.decode(await connection.recv())`:
    The tick loop's periodic broadcast (ws_server.py, ~20Hz) and a direct
    reply to a specific request (an Error, or the broadcast a completed
    move triggers) are sent via independent websocket.send() calls that
    race each other on the server side - discovered via a genuinely flaky
    test run where a spectator's Error reply arrived *after* an unrelated
    tick broadcast. A real client has the exact same problem and must
    dispatch by message content/type, never by "the next message must be
    the reply to what I just sent" - this helper is what a correct
    client (and Step 4's ClientCore) needs to do too.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise AssertionError("timed out waiting for a message matching the predicate")
        message = protocol.decode(await asyncio.wait_for(connection.recv(), timeout=remaining))
        if predicate(message):
            return message


def _is_error(message) -> bool:
    return isinstance(message, protocol.Error)


def _has_in_flight_motion(message) -> bool:
    return isinstance(message, protocol.GameStateUpdate) and len(message.motions) == 1


def test_two_clients_connect_concurrently_and_each_learns_its_own_color():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as first, \
                    websockets.connect(uri) as second:
                first_welcome = await _welcome(first)
                second_welcome = await _welcome(second)

                assert first_welcome.your_color == "w"
                assert second_welcome.your_color == "b"
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_server_reports_its_bound_port_when_started_on_port_zero():
    async def scenario():
        server, _ = await _start()
        try:
            assert server.port != 0
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_legal_move_broadcasts_updated_state_to_players_and_spectators():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as white, \
                    websockets.connect(uri) as black, \
                    websockets.connect(uri) as spectator:
                await _welcome(white)
                await _welcome(black)
                spectator_welcome = await _welcome(spectator)
                assert spectator_welcome.your_color is None

                move = protocol.MoveRequest(request_id="1", source=Position(6, 4), destination=Position(4, 4))
                await white.send(protocol.encode(move))

                # A successful request gets no direct reply (see
                # game_session.py: None means "accepted") - all three
                # connections instead receive the broadcast the accepted
                # move triggers, possibly interleaved with an unrelated
                # tick-loop broadcast that still shows no motion yet.
                white_update = await _recv_until(white, _has_in_flight_motion)
                black_update = await _recv_until(black, _has_in_flight_motion)
                spectator_update = await _recv_until(spectator, _has_in_flight_motion)

                for update in (white_update, black_update, spectator_update):
                    assert update.motions[0].source == Position(6, 4)
                    assert update.motions[0].destination == Position(4, 4)
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_illegal_move_returns_error_directly_to_the_sender():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as white:
                await _welcome(white)

                # A rook has no legal diagonal hop from its own starting cell.
                move = protocol.MoveRequest(request_id="1", source=Position(7, 0), destination=Position(5, 2))
                await white.send(protocol.encode(move))

                reply = await _recv_until(white, _is_error)
                assert reply == protocol.Error(reason="illegal_piece_move", request_id="1")
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_moving_the_opponents_piece_returns_wrong_color():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as white, \
                    websockets.connect(uri) as black:
                await _welcome(white)
                await _welcome(black)

                move = protocol.MoveRequest(request_id="1", source=Position(1, 4), destination=Position(3, 4))
                await white.send(protocol.encode(move))

                reply = await _recv_until(white, _is_error)
                assert reply == protocol.Error(reason="wrong_color", request_id="1")
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_spectator_move_request_is_rejected():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as white, \
                    websockets.connect(uri) as black, \
                    websockets.connect(uri) as spectator:
                await _welcome(white)
                await _welcome(black)
                await _welcome(spectator)

                move = protocol.MoveRequest(request_id="1", source=Position(6, 4), destination=Position(4, 4))
                await spectator.send(protocol.encode(move))

                reply = await _recv_until(spectator, _is_error)
                assert reply == protocol.Error(reason="spectators_cannot_move", request_id="1")
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_tick_loop_lands_an_accepted_motion_without_any_further_client_message():
    async def scenario():
        server, uri = await _start(tick_ms=100)
        try:
            async with websockets.connect(uri) as white:
                await _welcome(white)

                move = protocol.MoveRequest(request_id="1", source=Position(6, 4), destination=Position(4, 4))
                await white.send(protocol.encode(move))

                await _recv_until(white, _has_in_flight_motion)

                # Nothing else is sent from here on - only the server's
                # own tick loop can make the motion arrive.
                landed = await _recv_until(
                    white,
                    lambda m: isinstance(m, protocol.GameStateUpdate) and not m.motions,
                )
                assert any(
                    p.row == 4 and p.col == 4 and p.kind == "P" for p in landed.pieces
                )
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_connect_and_disconnect_are_logged_with_role_and_connection_count(capsys):
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as first:
                await _welcome(first)
                async with websockets.connect(uri) as second:
                    await _welcome(second)
        finally:
            await _stop(server)

    asyncio.run(scenario())

    out = capsys.readouterr().out
    assert "[connect] role=WHITE color=w connections=1" in out
    assert "[connect] role=BLACK color=b connections=2" in out
    assert "[disconnect] role=BLACK color=b connections=1" in out
    assert "[disconnect] role=WHITE color=w connections=0" in out