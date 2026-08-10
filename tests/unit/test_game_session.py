import pytest

from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import MatchFoundEvent
from kungfu_chess.model.position import Position
from kungfu_chess.network import protocol
from kungfu_chess.network.game_session import GameAlreadyEndedError, GameSession
from kungfu_chess.network.session import SessionManager, SessionState


def _game():
    """Every GameSession now takes an externally-owned SessionManager
    (see game_session.py's own docstring on why) - this builds the pair
    exactly the way WebSocketServer's composition root does, minus the
    GameSession sitting on the caller's side of the shared bus (tests
    publish MatchFoundEvent on it directly - see _match() below)."""
    bus = EventBus()
    return GameSession(SessionManager(bus)), bus


def _login(game: GameSession, connection, username: str):
    game.connect(connection)
    return game.login(connection, username)


def _match(game: GameSession, bus: EventBus,
           white_conn, white_username: str, black_conn, black_username: str):
    """Logs in two players (role=None each, per Step 2) and then matches
    them exactly like MatchmakingQueue would - publishing MatchFoundEvent
    on the same bus SessionManager subscribed to. Returns their (now
    role-assigned) Sessions - complete_login() already returned the same
    mutable Session objects the match mutates in place, so no re-fetch is
    needed."""
    white = _login(game, white_conn, white_username)
    black = _login(game, black_conn, black_username)
    bus.publish(MatchFoundEvent(white_username=white_username, black_username=black_username))
    return white, black


class _FakeEloService:
    def __init__(self):
        self.calls = []

    def record_game_result(self, white_username, black_username, winner_color):
        self.calls.append((white_username, black_username, winner_color))


def _capture_black_king(game: GameSession, white) -> None:
    """Drives a full legal move sequence through White's queenside rook
    that ends with it capturing Black's king - no shortcuts, no reaching
    into engine internals, since there is no check/checkmate/"illegal to
    expose your king" rule in this engine (see engine/notation.py) that
    would need working around. Exercises a real GameEndedEvent through
    GameSession's public API exactly the way a live game would produce
    one."""
    def move(source, destination):
        reply = game.handle_message(white, protocol.encode(
            protocol.MoveRequest(request_id="x", source=source, destination=destination)
        ))
        assert reply is None, f"unexpected rejection: {reply}"
        game.tick(5000)  # comfortably longer than any single leg below

    move(Position(6, 0), Position(4, 0))  # clear the rook's own pawn
    move(Position(7, 0), Position(5, 0))  # rook advances up the now-open file
    move(Position(5, 0), Position(5, 4))  # rook slides across to the e-file
    move(Position(5, 4), Position(1, 4))  # rook captures Black's e-pawn
    move(Position(1, 4), Position(0, 4))  # rook captures Black's king


def test_legal_move_from_correct_color_is_accepted():
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    reply = game.handle_message(white, protocol.encode(
        protocol.MoveRequest(request_id="1", source=Position(6, 4), destination=Position(4, 4))
    ))

    assert reply is None


def test_illegal_move_returns_engines_own_reason_with_the_request_id_echoed():
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    # A rook has no legal diagonal hop from its own starting cell.
    reply = game.handle_message(white, protocol.encode(
        protocol.MoveRequest(request_id="7", source=Position(7, 0), destination=Position(5, 2))
    ))

    assert reply == protocol.Error(reason="illegal_piece_move", request_id="7")


def test_move_on_a_piece_of_the_wrong_color_is_rejected_before_reaching_the_engine():
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    # (1, 4) is a black pawn; the sender is White.
    reply = game.handle_message(white, protocol.encode(
        protocol.MoveRequest(request_id="1", source=Position(1, 4), destination=Position(3, 4))
    ))

    assert reply == protocol.Error(reason="wrong_color", request_id="1")


def test_spectator_move_is_rejected_without_reaching_the_engine():
    game, bus = _game()
    _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    spectator = _login(game, "conn-spectator", "carol")  # game already active -> spectator

    reply = game.handle_message(spectator, protocol.encode(
        protocol.MoveRequest(request_id="1", source=Position(6, 4), destination=Position(4, 4))
    ))

    assert reply == protocol.Error(reason="spectators_cannot_move", request_id="1")


def test_spectator_jump_is_also_rejected():
    game, bus = _game()
    _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    spectator = _login(game, "conn-spectator", "carol")

    reply = game.handle_message(spectator, protocol.encode(
        protocol.JumpRequest(request_id="1", source=Position(6, 4))
    ))

    assert reply == protocol.Error(reason="spectators_cannot_move", request_id="1")


def test_two_requests_from_the_same_sender_are_each_rejected_with_their_own_request_id():
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    # Both target a black piece from White - both must be rejected, and
    # each Error must carry back the request_id of the specific request
    # that caused it, not the other one (see protocol.py's module
    # docstring on why request_id exists at all).
    first_reply = game.handle_message(white, protocol.encode(
        protocol.MoveRequest(request_id="A", source=Position(1, 0), destination=Position(2, 0))
    ))
    second_reply = game.handle_message(white, protocol.encode(
        protocol.MoveRequest(request_id="B", source=Position(1, 1), destination=Position(2, 1))
    ))

    assert first_reply == protocol.Error(reason="wrong_color", request_id="A")
    assert second_reply == protocol.Error(reason="wrong_color", request_id="B")


def test_malformed_json_returns_malformed_message_with_no_request_id():
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    reply = game.handle_message(white, "not json at all")

    assert reply == protocol.Error(reason="malformed_message", request_id=None)


def test_unrecognized_type_returns_unknown_message_type():
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    reply = game.handle_message(white, '{"type": "not_a_real_type"}')

    assert reply == protocol.Error(reason="unknown_message_type", request_id=None)


def test_server_to_client_message_type_sent_by_a_client_is_rejected():
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    reply = game.handle_message(white, protocol.encode(protocol.Error(reason="whatever")))

    assert reply == protocol.Error(reason="unknown_message_type", request_id=None)


def test_accepted_move_triggers_the_move_completed_callback():
    game, bus = _game()
    calls = []
    game.on_move_completed(lambda: calls.append(1))
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    game.handle_message(white, protocol.encode(
        protocol.MoveRequest(request_id="1", source=Position(6, 4), destination=Position(4, 4))
    ))

    assert calls == [1]


def test_rejected_move_does_not_trigger_the_move_completed_callback():
    game, bus = _game()
    calls = []
    game.on_move_completed(lambda: calls.append(1))
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    game.handle_message(white, protocol.encode(
        protocol.MoveRequest(request_id="1", source=Position(1, 4), destination=Position(3, 4))
    ))

    assert calls == []


def test_tick_advances_the_engine_and_a_completed_motion_lands():
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    game.handle_message(white, protocol.encode(
        protocol.MoveRequest(request_id="1", source=Position(6, 4), destination=Position(4, 4))
    ))

    still_in_flight = game.state_update_for(white)
    assert len(still_in_flight.motions) == 1

    game.tick(5000)  # comfortably longer than a 2-cell pawn advance

    landed = game.state_update_for(white)
    assert landed.motions == []
    assert any(p.row == 4 and p.col == 4 and p.kind == "P" for p in landed.pieces)


def test_state_update_for_carries_the_recipients_own_color():
    game, bus = _game()
    white, black = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    spectator = _login(game, "conn-spectator", "carol")

    assert game.state_update_for(white).your_color == "w"
    assert game.state_update_for(black).your_color == "b"
    assert game.state_update_for(spectator).your_color is None


def test_match_found_assigns_white_by_who_was_matched_first_regardless_of_login_order():
    """Role assignment now follows the match, not login/connect order at
    all - MatchFoundEvent's own white_username/black_username already
    encode who waited longer (matchmaking_queue.py); GameSession/
    SessionManager just apply it. Logging in "second" no longer means
    anything for role assignment the way it used to pre-Step-2."""
    game, bus = _game()
    game.connect("conn-first-to-connect")
    game.connect("conn-second-to-connect")
    first_login = game.login("conn-second-to-connect", "bob")
    second_login = game.login("conn-first-to-connect", "alice")
    assert first_login.role is None
    assert second_login.role is None

    bus.publish(MatchFoundEvent(white_username="alice", black_username="bob"))

    assert second_login.color == "w"  # alice
    assert first_login.color == "b"   # bob


def test_state_update_for_a_pending_not_yet_logged_in_session_has_no_color():
    game, _bus = _game()
    pending = game.connect("conn-1")

    assert pending.role is None
    assert game.state_update_for(pending).your_color is None


def test_state_update_for_a_logged_in_session_with_no_active_game_has_no_color():
    """The other, now-distinct way role ends up None: fully logged in,
    just nothing to play or watch yet (decision 6) - not the same state
    as test_state_update_for_a_pending_not_yet_logged_in_session_has_no_color."""
    game, _bus = _game()
    session = _login(game, "conn-1", "alice")

    assert session.is_logged_in is True
    assert game.state_update_for(session).your_color is None


def test_state_update_for_carries_both_players_usernames_identically_to_everyone():
    game, bus = _game()
    white, black = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    spectator = _login(game, "conn-spectator", "carol")

    for session in (white, black, spectator):
        update = game.state_update_for(session)
        assert update.white_username == "alice"
        assert update.black_username == "bob"


def test_state_update_for_has_no_remaining_seconds_while_everyone_is_connected():
    game, bus = _game()
    white, black = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    assert game.state_update_for(white).remaining_seconds is None
    assert game.state_update_for(black).remaining_seconds is None


def test_state_update_for_carries_remaining_seconds_once_a_player_disconnects():
    """feature/matchmaking-disconnect, Step 3: the countdown rides on the
    same GameStateUpdate everyone already receives (decision 8) -
    broadcast-identical, like white_username/black_username, not
    personalized like your_color."""
    game, bus = _game()
    white, black = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    game.disconnect("conn-white")

    for session in (white, black):
        update = game.state_update_for(session)
        assert update.remaining_seconds is not None
        assert update.remaining_seconds > 0


def test_state_update_for_has_no_remaining_seconds_after_a_spectator_disconnects():
    game, bus = _game()
    white, black = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    _login(game, "conn-spectator", "carol")

    game.disconnect("conn-spectator")

    assert game.state_update_for(white).remaining_seconds is None


def test_state_update_for_usernames_are_none_before_a_match_happens():
    game, _bus = _game()
    white = _login(game, "conn-white", "alice")

    update = game.state_update_for(white)
    assert update.white_username is None
    assert update.black_username is None


def test_king_capture_triggers_elo_update_with_both_usernames_and_winner():
    elo = _FakeEloService()
    bus = EventBus()
    game = GameSession(SessionManager(bus), elo_service=elo)
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    _capture_black_king(game, white)

    assert elo.calls == [("alice", "bob", "w")]


def test_game_ending_without_an_elo_service_does_not_raise():
    game, bus = _game()  # elo_service defaults to None
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    _capture_black_king(game, white)  # must not raise


def test_resign_on_disconnect_timeout_ends_the_game_for_the_opponent():
    game, bus = _game()
    white, black = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    game.disconnect("conn-white")

    game.resign_on_disconnect_timeout(white)

    update = game.state_update_for(black)
    assert update.game_over is True
    assert update.winner == "b"


def test_resign_on_disconnect_timeout_marks_the_session_resigned():
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    game.disconnect("conn-white")

    game.resign_on_disconnect_timeout(white)

    assert white.state is SessionState.RESIGNED


def test_resign_on_disconnect_timeout_updates_elo_exactly_like_a_regular_loss():
    """Decision 5: auto-resign uses the same EloService path as any other
    GameEndedEvent - reason differs, the ELO formula/call shape doesn't."""
    elo = _FakeEloService()
    bus = EventBus()
    game = GameSession(SessionManager(bus), elo_service=elo)
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    game.disconnect("conn-white")

    game.resign_on_disconnect_timeout(white)

    assert elo.calls == [("alice", "bob", "b")]


def test_no_moves_accepted_after_resign_on_disconnect_timeout():
    game, bus = _game()
    white, black = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    game.disconnect("conn-white")
    game.resign_on_disconnect_timeout(white)

    reply = game.handle_message(black, protocol.encode(
        protocol.MoveRequest(request_id="1", source=Position(1, 4), destination=Position(3, 4))
    ))

    assert reply == protocol.Error(reason="game_over", request_id="1")


def test_two_near_simultaneous_disconnect_timeouts_produce_only_one_winner():
    """Both colors disconnected and both timers eventually expire (the
    Step 4 design discussion) - whichever call reaches
    resign_on_disconnect_timeout() first decides the winner and the only
    EloService call; the second is a safe no-op purely because
    GameEngine.resign() already refuses to act once game_over is True -
    no extra guard needed here or in SessionManager."""
    elo = _FakeEloService()
    bus = EventBus()
    game = GameSession(SessionManager(bus), elo_service=elo)
    white, black = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    game.disconnect("conn-white")
    game.disconnect("conn-black")

    game.resign_on_disconnect_timeout(white)  # white's timer expires first
    game.resign_on_disconnect_timeout(black)  # black's own timer, moments later

    update = game.state_update_for(white)
    assert update.winner == "b"  # decided by the first call only
    assert elo.calls == [("alice", "bob", "b")]  # never called a second time
    assert white.state is SessionState.RESIGNED
    assert black.state is SessionState.RESIGNED  # still marked, even though ignored by the engine


def test_elo_service_is_not_called_if_a_color_never_logged_in():
    """Nobody ever became Black - simulated here by matching alice
    against a black_username that was never logged in. See
    session.py's _handle_match_found: a missing session on one side of a
    match is skipped rather than an error (the same defensive path a
    genuinely disconnected-while-queued player would hit - Step 3+). The
    board still has a black king to capture, but there's no black
    username to rate, so record_game_result must never be called."""
    elo = _FakeEloService()
    bus = EventBus()
    game = GameSession(SessionManager(bus), elo_service=elo)
    white = _login(game, "conn-white", "alice")
    bus.publish(MatchFoundEvent(white_username="alice", black_username="nobody"))

    _capture_black_king(game, white)

    assert elo.calls == []


# ---- reconnect (feature/matchmaking-disconnect, Step 5) ---------------

def test_reconnecting_returns_the_same_role_and_color():
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    game.disconnect("conn-white")

    game.connect("conn-white-new")  # what ws_server.py's _handle_connection does before login, every time
    reconnected = game.login("conn-white-new", "alice")

    assert reconnected is white  # same Session object, seat preserved
    assert reconnected.role == white.role
    assert reconnected.color == "w"
    assert reconnected.state is SessionState.ACTIVE


def test_reconnecting_wakes_the_pending_disconnect_timer():
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    game.disconnect("conn-white")

    game.connect("conn-white-new")
    game.login("conn-white-new", "alice")

    assert white.reconnected.is_set()


def test_reconnecting_gives_the_returning_client_the_full_snapshot():
    """Item ב: no new mechanism needed - state_update_for() already wraps
    a full snapshot, and works identically for a reconnected Session."""
    game, bus = _game()
    white, black = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    # A move happens while white is disconnected - black moves a pawn.
    game.disconnect("conn-white")
    game.handle_message(black, protocol.encode(
        protocol.MoveRequest(request_id="1", source=Position(1, 4), destination=Position(3, 4))
    ))
    game.tick(5000)

    game.connect("conn-white-new")
    reconnected = game.login("conn-white-new", "alice")

    update = game.state_update_for(reconnected)
    assert any(p.row == 3 and p.col == 4 and p.kind == "P" for p in update.pieces)


def test_reconnect_after_the_game_already_ended_by_auto_resign_is_rejected():
    """The straightforward case from item ג: the disconnect timer already
    fired (auto-resign, Step 4) before this reconnect attempt arrives -
    no race, just late."""
    game, bus = _game()
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    game.disconnect("conn-white")
    game.resign_on_disconnect_timeout(white)  # game_over is now True

    game.connect("conn-white-new")
    with pytest.raises(GameAlreadyEndedError) as exc_info:
        game.login("conn-white-new", "alice")
    assert exc_info.value.reason == "game_already_ended"


def test_reconnect_after_the_game_ended_by_a_king_capture_is_also_rejected():
    """A DISCONNECTED (not RESIGNED) seat whose game ended for a
    completely unrelated reason (a king capture landing while this
    player happened to be disconnected) - game_over is still the fact
    that matters, not this Session's own state."""
    game, bus = _game()
    white, black = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    game.disconnect("conn-black")
    _capture_black_king(game, white)  # game_over True, black's Session still just DISCONNECTED

    game.connect("conn-black-new")
    with pytest.raises(GameAlreadyEndedError) as exc_info:
        game.login("conn-black-new", "bob")
    assert exc_info.value.reason == "game_already_ended"


def test_resign_on_disconnect_timeout_is_a_no_op_if_already_reconnected():
    """The other half of the Step 5 race (item ג, verified in code, not
    assumed - see game_session.py's own docstring): a stale
    ReconnectTimeout firing after login() already reattached the
    connection in the asyncio.wait_for() cancellation gap must not
    resign a player who is, by the time this runs, already back."""
    elo = _FakeEloService()
    bus = EventBus()
    game = GameSession(SessionManager(bus), elo_service=elo)
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")
    game.disconnect("conn-white")
    game.connect("conn-white-new")
    game.login("conn-white-new", "alice")  # reconnected first, before the stale timer fires

    game.resign_on_disconnect_timeout(white)  # the timer that "lost" the race

    update = game.state_update_for(white)
    assert update.game_over is False
    assert white.state is SessionState.ACTIVE  # unchanged by the stale timeout
    assert elo.calls == []


def test_login_of_a_brand_new_username_is_unaffected_by_reconnect_handling():
    game, bus = _game()
    fresh = _login(game, "conn-1", "carol")
    assert fresh.role is None
    assert fresh.is_logged_in is True


def test_login_of_a_still_active_username_still_rejects_as_already_logged_in():
    from kungfu_chess.network.session import UsernameAlreadyLoggedInError
    game, bus = _game()
    _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    game.connect("conn-white-2")
    with pytest.raises(UsernameAlreadyLoggedInError) as exc_info:
        game.login("conn-white-2", "alice")  # alice is still ACTIVE on conn-white
    assert exc_info.value.reason == "already_logged_in"