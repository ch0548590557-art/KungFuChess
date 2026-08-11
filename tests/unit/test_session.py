import time

import pytest

from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import MatchFoundEvent
from kungfu_chess.network.session import (
    PlayerRole,
    SessionManager,
    SessionState,
    UsernameAlreadyLoggedInError,
)


class _ManagerWithBus(SessionManager):
    """Test-only convenience: keeps a handle on the EventBus a
    SessionManager was constructed with, so tests can publish a real
    MatchFoundEvent through the same subscribe()/publish() path
    production code uses - proving SessionManager actually wires itself
    up in __init__, not just that its handler method works in isolation."""

    def __init__(self):
        self.bus = EventBus()
        super().__init__(self.bus)


def _manager() -> _ManagerWithBus:
    return _ManagerWithBus()


def test_register_connection_creates_a_pending_session_with_no_role():
    manager = _manager()
    session = manager.register_connection("conn-1")

    assert session.role is None
    assert session.color is None
    assert session.is_logged_in is False


def test_login_no_longer_assigns_a_role():
    """The core Step 2 behavior change: a successful login only ever
    produces "connected, identified, no role" (or SPECTATOR - see the
    dedicated spectator tests below) - never WHITE/BLACK. Only a match
    ever does that (see test_match_found_assigns_white_and_black_below)."""
    manager = _manager()
    manager.register_connection("conn-1")

    session = manager.complete_login("conn-1", "alice")

    assert session.role is None
    assert session.color is None
    assert session.username == "alice"
    assert session.is_logged_in is True


def test_second_login_also_gets_no_role_while_no_game_is_active():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")

    session = manager.complete_login("conn-2", "bob")

    assert session.role is None
    assert session.is_logged_in is True


def test_login_while_a_game_is_active_becomes_a_spectator():
    manager = _manager()
    for conn in ("conn-1", "conn-2", "conn-3", "conn-4"):
        manager.register_connection(conn)
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, "alice", "bob")

    third = manager.complete_login("conn-3", "carol")
    fourth = manager.complete_login("conn-4", "dave")

    assert third.role is PlayerRole.SPECTATOR
    assert third.color is None
    assert fourth.role is PlayerRole.SPECTATOR
    assert fourth.color is None


def test_login_with_no_active_game_is_not_a_spectator():
    """Distinguishes the two now-different reasons role can be None: not
    logged in yet at all (see test_register_connection_... above) versus
    fully logged in with simply nothing to watch or play - decision 6's
    explicit "no game, no queue -> just connected"."""
    manager = _manager()
    manager.register_connection("conn-1")

    session = manager.complete_login("conn-1", "alice")

    assert session.is_logged_in is True
    assert session.role is None
    assert session.role is not PlayerRole.SPECTATOR


def test_complete_login_rejects_a_username_that_is_already_active():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.complete_login("conn-1", "alice")
    manager.register_connection("conn-2")

    with pytest.raises(UsernameAlreadyLoggedInError) as exc_info:
        manager.complete_login("conn-2", "alice")
    assert exc_info.value.reason == "already_logged_in"
    assert exc_info.value.username == "alice"

    # The first connection's session is untouched by the rejected second login.
    assert manager.username_for_role(PlayerRole.WHITE) is None  # nobody has a role yet
    first_session = manager._session_for_username("alice")
    assert first_session.connection == "conn-1"


def test_match_found_assigns_white_and_black():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")

    _publish_match(manager, white="alice", black="bob")

    alice = manager._session_for_username("alice")
    bob = manager._session_for_username("bob")
    assert alice.role is PlayerRole.WHITE
    assert alice.color == "w"
    assert bob.role is PlayerRole.BLACK
    assert bob.color == "b"


def test_match_found_clears_queued_bookkeeping_for_both_players():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    assert manager.begin_queueing("alice") is None
    assert manager.begin_queueing("bob") is None

    _publish_match(manager, white="alice", black="bob")

    # Both are now players, not queued - a later PlayRequest from either
    # must be rejected as already_playing, never already_in_queue.
    assert manager.begin_queueing("alice") == "already_playing"
    assert manager.begin_queueing("bob") == "already_playing"


def test_unregister_an_active_player_does_not_free_their_color():
    """feature/matchmaking-disconnect, Step 3: disconnecting no longer
    immediately vacates an active player's seat - see the module
    docstring. A new login while alice is DISCONNECTED still sees a
    fully-staffed game (both colors "taken"), so it becomes a spectator,
    not a promoted WHITE."""
    manager = _manager()
    manager.register_connection("conn-1")
    manager.complete_login("conn-1", "alice")
    manager.register_connection("conn-2")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")

    manager.unregister_connection("conn-1")

    manager.register_connection("conn-3")
    newcomer = manager.complete_login("conn-3", "carol")
    assert newcomer.role is PlayerRole.SPECTATOR


def test_unregister_does_not_touch_an_existing_spectators_role():
    manager = _manager()
    for conn in ("conn-1", "conn-2", "conn-3"):
        manager.register_connection(conn)
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")
    spectator = manager.complete_login("conn-3", "carol")
    assert spectator.role is PlayerRole.SPECTATOR

    manager.unregister_connection("conn-1")  # white leaves

    assert spectator.role is PlayerRole.SPECTATOR


def test_unregister_a_connection_that_never_logged_in_is_a_no_op():
    manager = _manager()
    manager.register_connection("conn-1")

    manager.unregister_connection("conn-1")  # must not raise, must not touch role_taken

    manager.register_connection("conn-2")
    replacement = manager.complete_login("conn-2", "alice")
    assert replacement.role is None  # nothing was ever taken, and no match happened either


def test_unregister_unknown_connection_is_a_no_op():
    manager = _manager()
    manager.unregister_connection("never-registered")  # must not raise


def test_username_for_role_is_none_before_anyone_has_a_role():
    manager = _manager()
    assert manager.username_for_role(PlayerRole.WHITE) is None
    assert manager.username_for_role(PlayerRole.BLACK) is None


def test_username_for_role_returns_the_matched_players_username():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")

    assert manager.username_for_role(PlayerRole.WHITE) == "alice"
    assert manager.username_for_role(PlayerRole.BLACK) == "bob"


def test_username_for_role_still_returns_a_disconnected_players_username():
    """feature/matchmaking-disconnect, Step 3: a disconnected active
    player's Session persists (see unregister_connection()'s docstring),
    so a GameStateUpdate broadcast can keep reporting who White/Black
    are - and that a resignation clock is running (remaining_seconds) -
    even though that player currently has no live connection at all."""
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")

    manager.unregister_connection("conn-1")

    assert manager.username_for_role(PlayerRole.WHITE) == "alice"


def test_begin_queueing_allows_a_fresh_username_and_marks_it_queued():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.complete_login("conn-1", "alice")

    assert manager.begin_queueing("alice") is None
    assert manager.begin_queueing("alice") == "already_in_queue"


def test_end_queueing_allows_a_later_play_request_again():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.complete_login("conn-1", "alice")
    manager.begin_queueing("alice")

    manager.end_queueing("alice")

    assert manager.begin_queueing("alice") is None


def test_end_queueing_for_a_never_queued_username_is_a_no_op():
    manager = _manager()
    manager.end_queueing("nobody")  # must not raise


def test_begin_queueing_rejects_a_current_player():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")

    assert manager.begin_queueing("alice") == "already_playing"


def test_begin_queueing_rejects_a_spectator_while_a_game_is_active():
    manager = _manager()
    for conn in ("conn-1", "conn-2", "conn-3"):
        manager.register_connection(conn)
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")
    spectator = manager.complete_login("conn-3", "carol")
    assert spectator.role is PlayerRole.SPECTATOR

    assert manager.begin_queueing("carol") == "game_in_progress"


def test_begin_queueing_prefers_already_in_queue_over_game_in_progress_when_both_apply():
    """already_playing/already_in_queue and game_in_progress are not
    mutually exclusive: alice can still be waiting in the queue at the
    exact moment two *other* players match each other and fill both
    colors - MatchmakingQueue resolves independently of alice's own
    entry. When both are true for the same username, already_in_queue
    must win - it's the specific fact about alice; game_in_progress is
    just a fact about the server that happens to be true right now
    regardless of who's asking (see begin_queueing()'s own docstring)."""
    manager = _manager()
    manager.register_connection("conn-alice")
    manager.complete_login("conn-alice", "alice")
    assert manager.begin_queueing("alice") is None  # alice queues first, no game active yet

    manager.register_connection("conn-bob")
    manager.register_connection("conn-carol")
    manager.complete_login("conn-bob", "bob")
    manager.complete_login("conn-carol", "carol")
    _publish_match(manager, white="bob", black="carol")  # a game becomes active without touching alice's entry

    assert manager.begin_queueing("alice") == "already_in_queue"


def test_unregister_while_queued_clears_the_already_in_queue_bookkeeping():
    """The Step 2 gap fixed first in Step 3: a role-less player who
    disconnects while queued (never matched, never timed out) must not
    stay blocked with already_in_queue forever - see the module
    docstring's note on unregister_connection() vs. the leak this
    closes."""
    manager = _manager()
    manager.register_connection("conn-1")
    manager.complete_login("conn-1", "alice")
    assert manager.begin_queueing("alice") is None  # alice is now queued

    manager.unregister_connection("conn-1")

    # A fresh PlayRequest under the same username (e.g. a later reconnect
    # attempt) must not be rejected as already_in_queue for a username
    # that no longer has any live session at all.
    assert manager.begin_queueing("alice") is None


def test_unregister_an_active_player_marks_disconnected_and_returns_the_session():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")

    result = manager.unregister_connection("conn-1")

    assert result is not None
    assert result.username == "alice"
    assert result.state is SessionState.DISCONNECTED
    assert result.disconnected_at is not None
    # The seat itself is untouched - role/color/username all persist.
    assert result.role is PlayerRole.WHITE
    assert result.color == "w"


def test_unregister_a_spectator_removes_immediately_with_no_timer():
    manager = _manager()
    for conn in ("conn-1", "conn-2", "conn-3"):
        manager.register_connection(conn)
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")
    manager.complete_login("conn-3", "carol")  # spectator - game already active

    result = manager.unregister_connection("conn-3")

    assert result is None  # nothing for the caller to start a timer for
    assert manager._session_for_username("carol") is None  # gone, not lingering


def test_unregister_a_role_less_connection_removes_immediately_with_no_timer():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.complete_login("conn-1", "alice")  # no active game -> role=None

    result = manager.unregister_connection("conn-1")

    assert result is None
    assert manager._session_for_username("alice") is None


def test_unregister_a_disconnected_player_a_second_time_returns_none():
    """Guard 7b: a flaky connection that closes twice (or any other
    double-close) must not start a second disconnect-timer task - the
    second unregister_connection() call for the same already-
    DISCONNECTED session is a no-op signal to the caller."""
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")

    first = manager.unregister_connection("conn-1")
    second = manager.unregister_connection("conn-1")

    assert first is not None
    assert second is None
    # The session itself is unaffected by the redundant second call.
    assert manager._session_for_username("alice").state is SessionState.DISCONNECTED


def test_remaining_disconnect_seconds_is_none_when_nobody_is_disconnected():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")

    assert manager.remaining_disconnect_seconds() is None


def test_remaining_disconnect_seconds_counts_down_with_real_elapsed_time():
    """Decision 8: no separate countdown timer/broadcast - the value is
    recomputed from real elapsed time on every call. A short
    disconnect_timeout_seconds keeps this test's real wall-clock cost
    small while still proving the value actually decreases (not frozen,
    not skipping) as time genuinely passes."""
    bus = EventBus()
    manager = SessionManager(bus, disconnect_timeout_seconds=2.0)
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    bus.publish(MatchFoundEvent(white_username="alice", black_username="bob"))

    manager.unregister_connection("conn-1")
    first_reading = manager.remaining_disconnect_seconds()
    assert first_reading is not None
    assert first_reading == 2  # ceil(2.0 - ~0) seconds

    time.sleep(1.1)
    second_reading = manager.remaining_disconnect_seconds()
    assert second_reading is not None
    assert second_reading < first_reading  # genuinely counted down
    assert second_reading == 1  # ceil(2.0 - ~1.1) seconds


def test_remaining_disconnect_seconds_floors_at_zero_once_past_the_deadline():
    bus = EventBus()
    manager = SessionManager(bus, disconnect_timeout_seconds=0.2)
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    bus.publish(MatchFoundEvent(white_username="alice", black_username="bob"))

    manager.unregister_connection("conn-1")
    time.sleep(0.4)  # comfortably past the 0.2s deadline

    # SessionManager itself never times anything out or calls
    # mark_resigned() on its own - that's GameSession's job, driven by a
    # real disconnect-timer task (see game_session.py's
    # resign_on_disconnect_timeout(), Step 4). Left alone, state simply
    # stays DISCONNECTED and the countdown floors at zero and stays
    # there, never negative, never None.
    assert manager.remaining_disconnect_seconds() == 0


def test_mark_resigned_transitions_state_and_leaves_the_seat_untouched():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")
    session = manager.unregister_connection("conn-1")

    manager.mark_resigned(session)

    assert session.state is SessionState.RESIGNED
    assert session.role is PlayerRole.WHITE
    assert session.color == "w"
    assert session.username == "alice"


def test_remaining_disconnect_seconds_ignores_a_resigned_session():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")
    session = manager.unregister_connection("conn-1")

    manager.mark_resigned(session)

    assert manager.remaining_disconnect_seconds() is None


# ---- reconnect (feature/matchmaking-disconnect, Step 5) ---------------

def test_reconnect_candidate_finds_a_disconnected_player():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")
    disconnected = manager.unregister_connection("conn-1")

    assert manager.reconnect_candidate("alice") is disconnected


def test_reconnect_candidate_is_none_for_an_active_player():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")

    assert manager.reconnect_candidate("alice") is None


def test_reconnect_candidate_is_none_for_an_unknown_username():
    manager = _manager()
    assert manager.reconnect_candidate("nobody") is None


def test_reconnect_candidate_also_matches_a_resigned_player():
    """A RESIGNED seat is still returned (not None) - by construction it
    always means game_over is already True (see the method's own
    docstring), so it's GameSession.login() that turns this into an
    accurate "game already ended" rejection rather than SessionManager
    leaving it to fall through to the misleading "already logged in"
    error a genuinely-ACTIVE duplicate gets."""
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")
    session = manager.unregister_connection("conn-1")
    manager.mark_resigned(session)

    assert manager.reconnect_candidate("alice") is session


def test_reconnect_reattaches_the_session_to_the_new_connection():
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")
    disconnected = manager.unregister_connection("conn-1")
    manager.register_connection("conn-1-new")  # what connect() does before login, every time

    result = manager.reconnect("conn-1-new", disconnected)

    assert result is disconnected  # same Session object, seat preserved
    assert result.connection == "conn-1-new"
    assert result.state is SessionState.ACTIVE
    assert result.disconnected_at is None
    assert result.role is PlayerRole.WHITE
    assert result.color == "w"
    assert result.username == "alice"
    assert result.reconnected.is_set()
    # The old connection key and the fresh pending Session connect()
    # created under the new key are both gone - only the reattached
    # Session, under its new key, remains.
    assert manager._session_for_username("alice") is result


def test_reconnect_wakes_a_pending_disconnect_timer():
    import asyncio

    async def scenario():
        manager = _manager()
        manager.register_connection("conn-1")
        manager.register_connection("conn-2")
        manager.complete_login("conn-1", "alice")
        manager.complete_login("conn-2", "bob")
        _publish_match(manager, white="alice", black="bob")
        disconnected = manager.unregister_connection("conn-1")
        manager.register_connection("conn-1-new")

        from kungfu_chess.network.disconnect_timer import await_reconnect_or_timeout
        timer = asyncio.ensure_future(await_reconnect_or_timeout(disconnected.reconnected, timeout_seconds=5.0))
        await asyncio.sleep(0)  # let the timer task actually start waiting

        manager.reconnect("conn-1-new", disconnected)

        await asyncio.wait_for(timer, timeout=1.0)  # must return normally, not raise ReconnectTimeout

    asyncio.run(scenario())


def test_a_second_disconnect_after_a_reconnect_gets_its_own_fresh_countdown():
    """Guards against reconnected staying permanently .set() after the
    first reconnect - see unregister_connection()'s own docstring on why
    it clears the Event on every fresh transition to DISCONNECTED."""
    manager = _manager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")
    _publish_match(manager, white="alice", black="bob")
    disconnected = manager.unregister_connection("conn-1")
    manager.register_connection("conn-1-new")
    manager.reconnect("conn-1-new", disconnected)
    assert disconnected.reconnected.is_set()

    second_disconnect = manager.unregister_connection("conn-1-new")

    assert second_disconnect is disconnected
    assert not disconnected.reconnected.is_set()


def _publish_match(manager: _ManagerWithBus, white: str, black: str) -> None:
    """Publishes on the same bus `manager` was constructed with, exactly
    like MatchmakingQueue would for a real match (see
    matchmaking_queue.py's own tests, which cover the matching/timing
    logic itself - this file only needs to prove SessionManager reacts
    correctly to the event, not re-derive it)."""
    manager.bus.publish(MatchFoundEvent(white_username=white, black_username=black))