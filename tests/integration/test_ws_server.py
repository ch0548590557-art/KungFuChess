import asyncio

import pytest
import websockets

from kungfu_chess.auth.auth_service import SqliteAuthService
from kungfu_chess.auth.sqlite_user_repository import SqliteUserRepository
from kungfu_chess.elo.elo_service import EloService
from kungfu_chess.model.position import Position
from kungfu_chess.network import protocol
from kungfu_chess.network.ws_server import WebSocketServer


async def _start(**kwargs):
    # A fresh in-memory UserRepository per server, shared by auth_service,
    # elo_service, and (feature/matchmaking-disconnect, Step 2) matchmaking
    # rating lookups - the same way _run_forever() shares one real
    # UserRepository between all three, so a login, a rating update, and a
    # PlayRequest all see the same users.
    user_repository = SqliteUserRepository(":memory:")
    auth_service = SqliteAuthService(user_repository)
    elo_service = EloService(user_repository)
    server = await WebSocketServer(auth_service, elo_service, user_repository, port=0, **kwargs).start()
    return server, f"ws://localhost:{server.port}"


async def _stop(server):
    server.close()
    await server.wait_closed()


async def _welcome(connection, username: str = "player", password: str = "hunter2") -> protocol.GameStateUpdate:
    """Registers a fresh `username` (every test starts a server with its
    own in-memory user DB via _start(), so the username is always new),
    then returns the personalized GameStateUpdate the server sends right
    after (see ws_server.py: the server withholds everything, including
    this welcome, until a RegisterRequest/LoginRequest arrives and
    AuthService accepts it). As of feature/matchmaking-disconnect Step 2,
    a successful login no longer assigns a role by itself - your_color on
    this particular update is always None unless a game was already
    active (see _match() below for the PlayRequest flow that assigns
    one)."""
    await connection.send(protocol.encode(protocol.RegisterRequest(username=username, password=password)))
    return protocol.decode(await connection.recv())


async def _relogin(connection, username: str, password: str = "hunter2") -> protocol.Message:
    """LoginRequest for an *existing* account (unlike _welcome(), which
    always registers a brand-new one) - used to reconnect on a fresh
    websocket after the original connection dropped. Returns whatever the
    server sends back first: a GameStateUpdate on a successful reconnect,
    or an Error (e.g. reason="game_already_ended") if it's rejected -
    callers decode the type themselves rather than this helper assuming
    success the way _welcome() can."""
    await connection.send(protocol.encode(protocol.LoginRequest(username=username, password=password)))
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


def _has_a_color(message) -> bool:
    return isinstance(message, protocol.GameStateUpdate) and message.your_color is not None


async def _match(first, second):
    """Sends PlayRequest on both (already logged-in) connections and
    waits for each to receive a GameStateUpdate showing it was assigned
    a color - the feature/matchmaking-disconnect Step 2 replacement for
    what login used to do by itself. `first` is given a head start (see
    decision 3: whoever waited longer in the queue becomes White) so
    callers can rely on `first` always ending up White, `second` Black -
    a real network round-trip has no other way to guarantee queue order
    deterministically."""
    await first.send(protocol.encode(protocol.PlayRequest()))
    await asyncio.sleep(0.1)
    await second.send(protocol.encode(protocol.PlayRequest()))

    first_update = await _recv_until(first, _has_a_color)
    second_update = await _recv_until(second, _has_a_color)
    return first_update, second_update


def test_play_request_matches_two_players_in_elo_range_white_is_whoever_waited_longer():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as first, \
                    websockets.connect(uri) as second:
                await _welcome(first, "alice")
                await _welcome(second, "bob")

                first_update, second_update = await _match(first, second)

                assert first_update.your_color == "w"   # alice queued first
                assert second_update.your_color == "b"  # bob queued second
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_play_request_order_determines_white_not_login_order():
    """Role assignment no longer follows login order at all (feature/
    matchmaking-disconnect, Step 2 - see session.py) - only queue-wait
    order does. Proves that even though `first_to_login` logs in first,
    if it sends PlayRequest *after* the other connection, it ends up
    Black."""
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as first_to_login, \
                    websockets.connect(uri) as second_to_login:
                await _welcome(first_to_login, "alice")
                await _welcome(second_to_login, "bob")

                # second_to_login queues first this time.
                second_update, first_update = await _match(second_to_login, first_to_login)

                assert second_update.your_color == "w"  # bob queued first
                assert first_update.your_color == "b"   # alice queued second
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_login_with_no_active_game_gets_no_role_and_is_not_queued():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as ws:
                welcome = await _welcome(ws, "alice")
                assert welcome.your_color is None

                # Not queued either - CancelPlayRequest is a safe no-op
                # (see protocol.py) with nothing to actually cancel.
                await ws.send(protocol.encode(protocol.CancelPlayRequest()))

                # Prove the connection is still alive and still logged in
                # as alice by sending a real request and getting a real
                # rejection back, not silence or a dropped connection.
                await ws.send(protocol.encode(
                    protocol.MoveRequest(request_id="1", source=Position(6, 4), destination=Position(4, 4))
                ))
                reply = await _recv_until(ws, _is_error)
                assert reply == protocol.Error(reason="wrong_color", request_id="1")
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_third_login_while_a_game_is_active_becomes_a_spectator_not_queued():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as white, \
                    websockets.connect(uri) as black:
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)

                # Opened only now, deliberately - its server-side login
                # timeout clock must not start ticking until the game is
                # actually active and this test is ready to use it (see
                # _welcome()'s docstring: connecting early but logging in
                # late risks tripping the default login timeout under any
                # system load, independent of anything this test asserts).
                async with websockets.connect(uri) as third:
                    third_welcome = await _welcome(third, "carol")
                    assert third_welcome.your_color is None  # spectator - no color

                    # Specifically SPECTATOR (rejected from moving), not
                    # merely role-less - see
                    # test_login_with_no_active_game_... above for the
                    # other, now-distinct "role is None" case.
                    await third.send(protocol.encode(
                        protocol.MoveRequest(request_id="1", source=Position(6, 4), destination=Position(4, 4))
                    ))
                    reply = await _recv_until(third, _is_error)
                    assert reply == protocol.Error(reason="spectators_cannot_move", request_id="1")
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_duplicate_login_for_an_already_active_username_is_rejected():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as first, \
                    websockets.connect(uri) as second:
                await _welcome(first, "alice", "hunter2")

                await second.send(protocol.encode(
                    protocol.LoginRequest(username="alice", password="hunter2"),
                ))
                reply = protocol.decode(await asyncio.wait_for(second.recv(), timeout=2.0))
                assert reply == protocol.Error(reason="already_logged_in")

                # The first connection is untouched - still alive, still
                # logged in as alice, not silently disconnected in favor
                # of the rejected second attempt.
                await first.send(protocol.encode(
                    protocol.MoveRequest(request_id="1", source=Position(7, 0), destination=Position(5, 2))
                ))
                reply = await _recv_until(first, _is_error)
                assert reply.reason != "login_required"
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_duplicate_play_request_while_queued_is_rejected():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as ws:
                await _welcome(ws, "alice")

                await ws.send(protocol.encode(protocol.PlayRequest()))
                await ws.send(protocol.encode(protocol.PlayRequest()))

                reply = await _recv_until(ws, _is_error)
                assert reply == protocol.Error(reason="already_in_queue")
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_play_request_from_an_already_playing_player_is_rejected():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as white, \
                    websockets.connect(uri) as black:
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)

                await white.send(protocol.encode(protocol.PlayRequest()))
                reply = await _recv_until(white, _is_error)
                assert reply == protocol.Error(reason="already_playing")

                # The active game is unaffected - white can still move.
                move = protocol.MoveRequest(request_id="1", source=Position(6, 4), destination=Position(4, 4))
                await white.send(protocol.encode(move))
                update = await _recv_until(white, _has_in_flight_motion)
                assert update.motions[0].source == Position(6, 4)
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_play_request_from_a_spectator_during_an_active_game_is_rejected():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as white, \
                    websockets.connect(uri) as black:
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)

                # Opened only now - see the identical note in
                # test_third_login_while_a_game_is_active_becomes_a_spectator_not_queued.
                async with websockets.connect(uri) as spectator:
                    await _welcome(spectator, "carol")

                    await spectator.send(protocol.encode(protocol.PlayRequest()))
                    reply = await _recv_until(spectator, _is_error)
                    assert reply == protocol.Error(reason="game_in_progress")
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_two_compatible_spectators_are_both_rejected_not_matched_with_each_other():
    """The exact scenario reviewed and confirmed before implementing
    Step 2: two spectators of an active game, well within ELO range of
    each other, must never produce a MatchFoundEvent - there is nowhere
    for it to go (a single active GameSession, both colors already
    taken, and no Rooms/multi-game support in this layer)."""
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as white, \
                    websockets.connect(uri) as black:
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)

                # Opened only now - see the identical note in
                # test_third_login_while_a_game_is_active_becomes_a_spectator_not_queued.
                async with websockets.connect(uri) as spec1, \
                        websockets.connect(uri) as spec2:
                    await _welcome(spec1, "carol")
                    await _welcome(spec2, "dave")

                    await spec1.send(protocol.encode(protocol.PlayRequest()))
                    await spec2.send(protocol.encode(protocol.PlayRequest()))

                    reply1 = await _recv_until(spec1, _is_error)
                    reply2 = await _recv_until(spec2, _is_error)
                    assert reply1 == protocol.Error(reason="game_in_progress")
                    assert reply2 == protocol.Error(reason="game_in_progress")

                    # Neither was actually queued/matched - no GameStateUpdate
                    # assigning either of them a color ever arrives. (Whichever
                    # of AssertionError/TimeoutError surfaces depends on exactly
                    # where _recv_until's deadline check lands - both mean the
                    # same thing here: nothing matching ever showed up.)
                    with pytest.raises((AssertionError, TimeoutError)):
                        await _recv_until(spec1, _has_a_color, timeout=0.3)
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_client_that_never_logs_in_gets_a_timeout_error_and_is_disconnected():
    async def scenario():
        server, uri = await _start(login_timeout_seconds=0.3)
        try:
            async with websockets.connect(uri) as ws:
                # Deliberately never send a LoginRequest - this is the
                # "client never sends login" scenario: the server must
                # degrade to a clean timeout, not hang forever waiting
                # (and the client must not deadlock waiting on a welcome
                # that will never come, since it never asked for one).
                reply = protocol.decode(await asyncio.wait_for(ws.recv(), timeout=2.0))
                assert reply == protocol.Error(reason="login_timeout")

                # The server closes the connection right after sending
                # that - a further recv() must fail, not hang.
                with pytest.raises(websockets.exceptions.ConnectionClosed):
                    await asyncio.wait_for(ws.recv(), timeout=2.0)
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_client_that_sends_garbage_before_logging_in_is_rejected():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as ws:
                await ws.send("not json at all")
                reply = protocol.decode(await asyncio.wait_for(ws.recv(), timeout=2.0))
                assert reply == protocol.Error(reason="malformed_message")
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_client_that_sends_a_move_before_logging_in_is_rejected():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as ws:
                move = protocol.MoveRequest(
                    request_id="1", source=Position(6, 4), destination=Position(4, 4),
                )
                await ws.send(protocol.encode(move))
                reply = protocol.decode(await asyncio.wait_for(ws.recv(), timeout=2.0))
                assert reply == protocol.Error(reason="login_required")
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_registering_an_already_taken_username_is_rejected():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as first, \
                    websockets.connect(uri) as second:
                await _welcome(first, "alice", "hunter2")

                await second.send(protocol.encode(
                    protocol.RegisterRequest(username="alice", password="different password"),
                ))
                reply = protocol.decode(await asyncio.wait_for(second.recv(), timeout=2.0))
                assert reply == protocol.Error(reason="username_taken")
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_logging_in_with_the_wrong_password_is_rejected():
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as first, \
                    websockets.connect(uri) as second:
                await _welcome(first, "alice", "hunter2")

                await second.send(protocol.encode(
                    protocol.LoginRequest(username="alice", password="wrong password"),
                ))
                reply = protocol.decode(await asyncio.wait_for(second.recv(), timeout=2.0))
                assert reply == protocol.Error(reason="invalid_credentials")
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
                    websockets.connect(uri) as black:
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)

                # Opened only now - see the identical note in
                # test_third_login_while_a_game_is_active_becomes_a_spectator_not_queued.
                async with websockets.connect(uri) as spectator:
                    spectator_welcome = await _welcome(spectator, "carol")
                    assert spectator_welcome.your_color is None

                    move = protocol.MoveRequest(
                        request_id="1", source=Position(6, 4), destination=Position(4, 4),
                    )
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
            async with websockets.connect(uri) as white, \
                    websockets.connect(uri) as black:
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)

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
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)

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
                    websockets.connect(uri) as black:
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)

                # Opened only now - see the identical note in
                # test_third_login_while_a_game_is_active_becomes_a_spectator_not_queued.
                async with websockets.connect(uri) as spectator:
                    await _welcome(spectator, "carol")

                    move = protocol.MoveRequest(
                        request_id="1", source=Position(6, 4), destination=Position(4, 4),
                    )
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
            async with websockets.connect(uri) as white, \
                    websockets.connect(uri) as black:
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)

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


def test_connect_and_disconnect_are_logged_with_username_role_and_connection_count(capsys):
    async def scenario():
        server, uri = await _start()
        try:
            async with websockets.connect(uri) as first:
                await _welcome(first, "alice")
                async with websockets.connect(uri) as second:
                    await _welcome(second, "bob")
                    await _match(first, second)
        finally:
            await _stop(server)

    asyncio.run(scenario())

    out = capsys.readouterr().out
    # Login no longer assigns a role by itself (feature/matchmaking-
    # disconnect, Step 2) - connect logs show NONE until PlayRequest
    # results in a match; disconnect logs then show the roles the match
    # actually assigned, proving the printed state is live, not stale.
    assert "[connect] username=alice role=NONE color=None connections=1" in out
    assert "[connect] username=bob role=NONE color=None connections=2" in out
    assert "[disconnect] username=bob role=BLACK color=b connections=1" in out
    assert "[disconnect] username=alice role=WHITE color=w connections=0" in out


def test_active_player_disconnect_starts_a_countdown_visible_to_the_other_player():
    """feature/matchmaking-disconnect, Step 3, end-to-end: white's
    connection drops unexpectedly (not a graceful close message - just
    the socket going away, like a real dropped connection) and black,
    still connected, sees a countdown appear on a later broadcast."""
    async def scenario():
        server, uri = await _start(tick_ms=50)
        try:
            async with websockets.connect(uri) as black:
                async with websockets.connect(uri) as white:
                    await _welcome(white, "alice")
                    await _welcome(black, "bob")
                    await _match(white, black)
                # white's `async with` block just exited - its connection
                # is now closed, exactly like an unexpected disconnect.

                update = await _recv_until(
                    black,
                    lambda m: isinstance(m, protocol.GameStateUpdate) and m.remaining_seconds is not None,
                )
                assert update.remaining_seconds > 0
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_disconnect_timeout_auto_resigns_in_favor_of_the_opponent():
    """feature/matchmaking-disconnect, Step 4, end-to-end: white drops
    and never reconnects - once a short disconnect_timeout_seconds
    actually elapses, black sees the game end in their favor via the same
    GameStateUpdate.game_over/winner fields a king-capture ending would
    set. See test_reconnecting_before_the_timeout_resumes_the_same_game
    (Step 5) for the case where white *does* come back in time."""
    async def scenario():
        server, uri = await _start(tick_ms=50, disconnect_timeout_seconds=0.3)
        try:
            async with websockets.connect(uri) as black:
                async with websockets.connect(uri) as white:
                    await _welcome(white, "alice")
                    await _welcome(black, "bob")
                    await _match(white, black)
                # white's `async with` block just exited - connection gone.

                # 10s margin: verified live that a bare localhost
                # websockets.connect() can intermittently take ~2s per
                # connection here, unrelated to this server.
                update = await _recv_until(
                    black,
                    lambda m: isinstance(m, protocol.GameStateUpdate) and m.game_over,
                    timeout=10.0,
                )
                assert update.winner == "b"
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_spectator_disconnect_does_not_start_a_countdown():
    async def scenario():
        server, uri = await _start(tick_ms=50)
        try:
            async with websockets.connect(uri) as white, \
                    websockets.connect(uri) as black:
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)

                async with websockets.connect(uri) as spectator:
                    await _welcome(spectator, "carol")
                # spectator's connection just closed - no role, no timer.

                with pytest.raises((AssertionError, TimeoutError)):
                    await _recv_until(
                        white,
                        lambda m: isinstance(m, protocol.GameStateUpdate) and m.remaining_seconds is not None,
                        timeout=0.5,
                    )
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_reconnecting_before_the_timeout_resumes_the_same_game():
    """feature/matchmaking-disconnect, Step 5, end-to-end: white drops
    (an unexpected close, not a graceful logout) and reconnects on a
    fresh websocket with the same username/password before the
    disconnect timer expires - same role/color, timer cancelled, and
    still able to play (item ב/ד)."""
    async def scenario():
        # Generous disconnect_timeout_seconds: verified live (Step 4
        # testing notes) that a bare localhost connect() can
        # intermittently cost ~2s here, unrelated to this server - the
        # reconnect below opens a brand-new connection and must comfortably
        # land inside the window.
        server, uri = await _start(tick_ms=50, disconnect_timeout_seconds=8.0)
        try:
            async with websockets.connect(uri) as black:
                white = await websockets.connect(uri)
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)
                await white.close()  # unexpected drop, not a graceful logout

                # Proves this is a genuine disconnect (the countdown
                # actually started), not a reconnect so fast the timer
                # never ran.
                await _recv_until(
                    black,
                    lambda m: isinstance(m, protocol.GameStateUpdate) and m.remaining_seconds is not None,
                    timeout=10.0,
                )

                white_new = await websockets.connect(uri)
                try:
                    welcome_back = await _relogin(white_new, "alice")
                    assert isinstance(welcome_back, protocol.GameStateUpdate)
                    assert welcome_back.your_color == "w"
                    assert welcome_back.game_over is False
                    assert welcome_back.remaining_seconds is None  # timer cancelled

                    # Black's broadcasts eventually settle back to no
                    # countdown too - a positive "reaches None" check
                    # (not "never see remaining_seconds again for 0.5s"):
                    # black's socket can still have a backlog of
                    # already-sent, not-yet-read ticks from *before* the
                    # reconnect actually completed (each carrying a real,
                    # not-yet-stale remaining_seconds at the time it was
                    # sent) queued up, especially if the reconnect
                    # round-trip itself was slow - a negative check would
                    # wrongly treat draining that backlog as a bug.
                    settled = await _recv_until(
                        black,
                        lambda m: isinstance(m, protocol.GameStateUpdate) and m.remaining_seconds is None,
                        timeout=10.0,
                    )
                    assert settled.remaining_seconds is None

                    # The reconnected connection can still actually play.
                    move = protocol.MoveRequest(
                        request_id="1", source=Position(6, 4), destination=Position(4, 4),
                    )
                    await white_new.send(protocol.encode(move))
                    landed = await _recv_until(white_new, _has_in_flight_motion)
                    assert landed.motions[0].source == Position(6, 4)
                finally:
                    await white_new.close()
        finally:
            await _stop(server)

    asyncio.run(scenario())


def test_reconnect_after_the_disconnect_timeout_already_fired_is_rejected():
    """feature/matchmaking-disconnect, Step 5, end-to-end, item ג: white
    drops, the (short) disconnect timer actually expires and auto-resigns
    them (Step 4), and *then* white tries to reconnect - must fail
    clearly, not resume a game that already ended."""
    async def scenario():
        server, uri = await _start(tick_ms=50, disconnect_timeout_seconds=0.3)
        try:
            async with websockets.connect(uri) as black:
                white = await websockets.connect(uri)
                await _welcome(white, "alice")
                await _welcome(black, "bob")
                await _match(white, black)
                await white.close()

                # 10s margin - see the note on the analogous auto-resign
                # test above.
                update = await _recv_until(
                    black,
                    lambda m: isinstance(m, protocol.GameStateUpdate) and m.game_over,
                    timeout=10.0,
                )
                assert update.winner == "b"

                white_new = await websockets.connect(uri)
                try:
                    reply = await _relogin(white_new, "alice")
                    assert reply == protocol.Error(reason="game_already_ended")
                finally:
                    await white_new.close()
        finally:
            await _stop(server)

    asyncio.run(scenario())

# A live test that rapidly cycles many sockets in a tight loop, racing
# reconnect against a very short disconnect timer, was tried here and
# dropped: verified (not assumed - see this branch's Step 5 testing
# notes) that the tight cycling itself, not this feature, occasionally
# triggers an ~80s stall on this Windows machine (a worse version of the
# same localhost-connect quirk already documented on the Step 4 auto-
# resign test) - every one of those runs still passed its assertions, so
# it was never a correctness signal, only a suite-reliability cost. The
# exact race resign_on_disconnect_timeout() guards against is already
# exercised deterministically by
# test_resign_on_disconnect_timeout_is_a_no_op_if_already_reconnected
# (unit, test_game_session.py).