"""feature/matchmaking-disconnect, Step 7: concurrency/interaction tests.

These don't belong to any single Step - each one exercises a race
between two Steps' own mechanisms (MatchmakingQueue x SessionManager,
disconnect x reconnect, ...) that no single Step's own test file is the
right place for. No new behavior is introduced here; every guard these
tests exercise already exists (cited in each test's docstring) - this
file's job is to prove those guards hold under the specific tight
timings the original plan called out, not to add new ones.

WHY THESE RACES ARE TESTABLE DETERMINISTICALLY, NOT VIA LUCKY TIMING:
Every guard under test here lives inside code that never awaits between
the check and the state change it protects (the same guard-7c reasoning
already established across session.py/game_session.py/game_engine.py's
own docstrings: one event loop, cooperative scheduling, so "at the same
moment" always resolves to a deterministic call order, never a true
data race). Each test below reproduces that order explicitly (do X,
then Y, assert the outcome) rather than hoping two real timers fire
close enough together - the same style test_matchmaking_queue.py's own
race tests already use.
"""
import asyncio

import pytest

from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import MatchFoundEvent
from kungfu_chess.matchmaking.matchmaking_queue import MatchmakingQueue, MatchmakingTimeout
from kungfu_chess.network.game_session import GameSession
from kungfu_chess.network.session import (
    PlayerRole,
    SessionManager,
    SessionState,
    UsernameAlreadyLoggedInError,
)


def _login(game: GameSession, connection, username: str):
    game.connect(connection)
    return game.login(connection, username)


def _match(game: GameSession, bus: EventBus,
           white_conn, white_username: str, black_conn, black_username: str):
    white = _login(game, white_conn, white_username)
    black = _login(game, black_conn, black_username)
    bus.publish(MatchFoundEvent(white_username=white_username, black_username=black_username))
    return white, black


# ---- 1. Disconnect while still queued (cross-cutting: MatchmakingQueue x
#         SessionManager x ws_server.py's disconnect orchestration) -------

def test_disconnect_while_queued_cleans_up_both_matchmaking_and_session_state():
    """A dedicated test for the exact combination ws_server.py's
    disconnect path performs (MatchmakingQueue.cancel() +
    SessionManager.end_queueing() + unregister_connection(), all three -
    see the bugfix commit) - not MatchmakingQueue.cancel() alone
    (already covered in test_matchmaking_queue.py's own cancel tests)
    and not only the indirect "a later pair can still match" symptom
    the original regression test (test_ws_server.py) caught. Checks
    both halves of the contract behaviorally: the disconnected player's
    own enqueue() call resolves cleanly instead of timing out, AND
    SessionManager no longer considers that username queued."""
    async def scenario():
        bus = EventBus()
        sessions = SessionManager(bus)
        matchmaking = MatchmakingQueue(bus, timeout_seconds=5.0)

        sessions.register_connection("conn-alice")
        sessions.complete_login("conn-alice", "alice")
        assert sessions.begin_queueing("alice") is None
        task = asyncio.ensure_future(matchmaking.enqueue("alice", 1200))
        await asyncio.sleep(0)  # alice is now genuinely waiting in the queue

        # Exactly what _handle_connection()'s finally block does on a
        # disconnect (ws_server.py) - all three calls, not just one.
        matchmaking.cancel("alice")
        sessions.end_queueing("alice")
        sessions.unregister_connection("conn-alice")

        await task  # must resolve normally - proves cancel() actually ran

        # SessionManager's own bookkeeping is clean too: a fresh
        # login+PlayRequest for the same username is allowed again, not
        # rejected as "already_in_queue".
        sessions.register_connection("conn-alice-2")
        sessions.complete_login("conn-alice-2", "alice")
        assert sessions.begin_queueing("alice") is None

    asyncio.run(scenario())


def test_disconnect_while_queued_does_not_block_an_unrelated_later_pair():
    """The MatchmakingQueue-only half of the same guarantee, proven the
    same indirect way test_matchmaking_queue.py's own ghost-entry test
    does: if alice's entry had been left behind, bob would match her
    ghost instead of carol."""
    async def scenario():
        bus = EventBus()
        received = []
        bus.subscribe(MatchFoundEvent, received.append)
        matchmaking = MatchmakingQueue(bus, timeout_seconds=5.0)

        task = asyncio.ensure_future(matchmaking.enqueue("alice", 1200))
        await asyncio.sleep(0)
        matchmaking.cancel("alice")  # alice "disconnects" while still queued
        await task

        bob_task = asyncio.ensure_future(matchmaking.enqueue("bob", 1200))
        await asyncio.sleep(0)
        await matchmaking.enqueue("carol", 1200)
        await bob_task

        assert received == [MatchFoundEvent(white_username="bob", black_username="carol")]

    asyncio.run(scenario())


# ---- 2. Cancel arriving just after a match was already found ------------

def test_cancel_arriving_just_after_a_match_leaves_the_session_correctly_matched():
    """Cross-cutting: MatchmakingQueue.cancel() already no-ops safely
    once a match has happened (test_matchmaking_queue.py's own
    test_cancel_after_the_player_is_already_matched_is_a_safe_no_op) -
    this checks the *system* stays consistent too: SessionManager must
    already have assigned the real role by the time a "too late"
    CancelPlayRequest arrives, so the player ends up in the game, never
    stuck neither-queued-nor-playing."""
    async def scenario():
        bus = EventBus()
        sessions = SessionManager(bus)
        matchmaking = MatchmakingQueue(bus, timeout_seconds=5.0)
        for conn, name in (("conn-alice", "alice"), ("conn-bob", "bob")):
            sessions.register_connection(conn)
            sessions.complete_login(conn, name)
            sessions.begin_queueing(name)

        task = asyncio.ensure_future(matchmaking.enqueue("alice", 1200))
        await asyncio.sleep(0)
        await matchmaking.enqueue("bob", 1200)  # matches alice immediately
        await task
        sessions.end_queueing("alice")
        sessions.end_queueing("bob")

        # A CancelPlayRequest for alice arrives right after - too late.
        removed = matchmaking.cancel("alice")
        sessions.end_queueing("alice")  # what ws_server.py's cancel handler always does too

        assert removed is False  # nothing to cancel - she was never re-queued
        alice_session = sessions._session_for_username("alice")
        assert alice_session.role is PlayerRole.WHITE  # untouched by the late cancel
        assert alice_session.color == "w"

    asyncio.run(scenario())


# ---- 3. Two near-simultaneous logins for the same username --------------

def test_two_near_simultaneous_logins_for_the_same_username_are_deterministic():
    """complete_login() never awaits, so two calls for the same username
    can never truly interleave (guard 7c) - exactly one must always
    succeed, and it must be whichever one is actually called first, in
    *either* ordering. Proven by running both orderings, not just one -
    a test that only tried "conn-1 then conn-2" couldn't tell a real
    first-caller-wins guarantee apart from "conn-1 always happens to
    win"."""
    for winner_conn, loser_conn in (("conn-1", "conn-2"), ("conn-2", "conn-1")):
        manager = SessionManager(EventBus())
        manager.register_connection("conn-1")
        manager.register_connection("conn-2")

        winner_session = manager.complete_login(winner_conn, "alice")
        with pytest.raises(UsernameAlreadyLoggedInError) as exc_info:
            manager.complete_login(loser_conn, "alice")

        assert exc_info.value.reason == "already_logged_in"
        assert winner_session.username == "alice"
        assert winner_session.connection == winner_conn


# ---- 4. Disconnecting the same connection twice, at the GameSession -----
#         facade ws_server.py actually calls (guard 7b) ------------------

def test_disconnecting_the_same_connection_twice_via_gamesession_is_safe():
    """Direct simulation of guard 7b at GameSession.disconnect() - the
    facade ws_server.py actually calls - rather than only at
    SessionManager.unregister_connection() directly (already covered in
    test_session.py's own test_unregister_a_disconnected_player_a_
    second_time_returns_none). A flaky connection reporting "closed"
    twice must start exactly one disconnect-timer task, never two."""
    bus = EventBus()
    game = GameSession(SessionManager(bus))
    white, _ = _match(game, bus, "conn-white", "alice", "conn-black", "bob")

    first = game.disconnect("conn-white")
    second = game.disconnect("conn-white")

    assert first is white  # the real, first disconnect - ws_server.py starts a timer
    assert second is None  # the redundant second one - guard 7b, no second timer
    assert white.state is SessionState.DISCONNECTED  # unaffected by the redundant call
    assert white.role is PlayerRole.WHITE
    assert white.color == "w"


# ---- 5. Matchmaking timeout firing in the same instant a match lands ----

def test_match_found_at_the_tightest_possible_timing_still_beats_the_timeout():
    """test_timeout_is_cancelled_and_never_fires_once_a_match_is_found
    (test_matchmaking_queue.py) already proves this with a comfortable
    0.05s window. timeout_seconds=0.0 here is the tightest timing this
    guard can ever actually be asked to resolve - the match still wins
    deterministically, not by luck: _match() sets entry.matched
    synchronously, with no `await` in between, as part of the *same*
    synchronous burst that runs when the second enqueue() call finds an
    opponent - nothing can interleave enough for the near-zero timeout
    to be observed first (see this module's own docstring)."""
    async def scenario():
        bus = EventBus()
        received = []
        bus.subscribe(MatchFoundEvent, received.append)
        queue = MatchmakingQueue(bus, timeout_seconds=0.0)

        results = {}

        async def waiter():
            try:
                await queue.enqueue("alice", 1000)
                results["alice"] = "matched"
            except MatchmakingTimeout:
                results["alice"] = "timeout"

        task = asyncio.ensure_future(waiter())
        await asyncio.sleep(0)  # alice is now waiting, her 0.0s timeout already scheduled

        await queue.enqueue("bob", 1000)  # matches immediately, synchronously
        await task

        assert results["alice"] == "matched"
        assert received == [MatchFoundEvent(white_username="alice", black_username="bob")]

    asyncio.run(scenario())


# ---- 6. Disconnect timer expiring exactly as a reconnect arrives --------
#
# Already covered directly, at the tight timing the plan calls out, by
# test_game_session.py's test_resign_on_disconnect_timeout_is_a_no_op_
# if_already_reconnected (Step 5): it reconnects a session and *then*
# fires the stale disconnect-timeout callback for it, asserting the
# resign is a no-op and the session stays ACTIVE - exactly this race.
# Not duplicated here.