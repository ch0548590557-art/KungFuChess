import asyncio

import pytest

from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import MatchFoundEvent
from kungfu_chess.matchmaking.matchmaking_queue import MatchmakingQueue, MatchmakingTimeout


def _queue(bus=None, rating_range=100, timeout_seconds=1.0):
    return MatchmakingQueue(
        bus if bus is not None else EventBus(),
        rating_range=rating_range,
        timeout_seconds=timeout_seconds,
    )


def test_two_players_within_range_are_matched_and_publish_match_found_event():
    async def scenario():
        bus = EventBus()
        received = []
        bus.subscribe(MatchFoundEvent, received.append)
        queue = _queue(bus)

        task = asyncio.ensure_future(queue.enqueue("alice", 1000))
        await asyncio.sleep(0)  # let alice actually start waiting in the queue

        await queue.enqueue("bob", 1080)  # within the default +-100 range
        await task

        assert received == [MatchFoundEvent(white_username="alice", black_username="bob")]

    asyncio.run(scenario())


def test_whoever_waited_longer_is_assigned_white():
    async def scenario():
        bus = EventBus()
        received = []
        bus.subscribe(MatchFoundEvent, received.append)
        queue = _queue(bus)

        task = asyncio.ensure_future(queue.enqueue("bob", 1000))
        await asyncio.sleep(0)

        await queue.enqueue("alice", 1000)
        await task

        assert received[0].white_username == "bob"
        assert received[0].black_username == "alice"

    asyncio.run(scenario())


def test_players_outside_rating_range_are_not_matched():
    async def scenario():
        bus = EventBus()
        received = []
        bus.subscribe(MatchFoundEvent, received.append)
        queue = _queue(bus, rating_range=100, timeout_seconds=0.05)

        task = asyncio.ensure_future(queue.enqueue("alice", 1000))
        await asyncio.sleep(0)

        with pytest.raises(MatchmakingTimeout):
            await queue.enqueue("bob", 1200)  # 200 apart - outside range, also times out

        with pytest.raises(MatchmakingTimeout):
            await task

        assert received == []

    asyncio.run(scenario())


def test_timeout_fires_when_no_opponent_ever_shows_up():
    async def scenario():
        queue = _queue(timeout_seconds=0.05)
        with pytest.raises(MatchmakingTimeout) as exc_info:
            await queue.enqueue("alice", 1000)
        assert exc_info.value.username == "alice"

    asyncio.run(scenario())


def test_timeout_is_cancelled_and_never_fires_once_a_match_is_found():
    async def scenario():
        bus = EventBus()
        received = []
        bus.subscribe(MatchFoundEvent, received.append)
        queue = _queue(bus, timeout_seconds=0.05)

        results = {}

        async def waiter():
            try:
                await queue.enqueue("alice", 1000)
                results["alice"] = "matched"
            except MatchmakingTimeout:
                results["alice"] = "timeout"

        task = asyncio.ensure_future(waiter())
        await asyncio.sleep(0)  # alice is now waiting, well inside the 0.05s window

        await queue.enqueue("bob", 1000)  # matches immediately
        await task

        # Wait well past alice's original timeout window - if it hadn't been
        # explicitly cancelled, nothing further should happen anyway (alice's
        # coroutine already finished), but this guards against a regression
        # where enqueue() returns MatchmakingTimeout despite already matching.
        await asyncio.sleep(0.2)

        assert results["alice"] == "matched"
        assert len(received) == 1

    asyncio.run(scenario())


def test_cancel_removes_a_waiting_player_without_matching_or_raising():
    async def scenario():
        bus = EventBus()
        received = []
        bus.subscribe(MatchFoundEvent, received.append)
        queue = _queue(bus, timeout_seconds=1.0)

        task = asyncio.ensure_future(queue.enqueue("alice", 1000))
        await asyncio.sleep(0)

        removed = queue.cancel("alice")
        await task  # returns normally, no exception

        assert removed is True
        assert received == []

    asyncio.run(scenario())


def test_cancel_is_idempotent_when_the_player_is_not_queued():
    queue = _queue()
    assert queue.cancel("nobody") is False

    async def scenario():
        task = asyncio.ensure_future(queue.enqueue("alice", 1000))
        await asyncio.sleep(0)

        assert queue.cancel("alice") is True
        assert queue.cancel("alice") is False  # already removed - must not raise
        await task

    asyncio.run(scenario())


def test_cancelling_the_awaiting_task_from_outside_leaves_no_ghost_entry():
    async def scenario():
        bus = EventBus()
        received = []
        bus.subscribe(MatchFoundEvent, received.append)
        queue = _queue(bus, timeout_seconds=0.05)

        task = asyncio.ensure_future(queue.enqueue("alice", 1000))
        await asyncio.sleep(0)  # alice is now queued and waiting

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # If alice's entry had been left as a "ghost" in the queue, bob
        # would be matched with it immediately instead of timing out - this
        # proves the queue itself was cleaned up, not just that alice's own
        # call returned.
        with pytest.raises(MatchmakingTimeout):
            await queue.enqueue("bob", 1000)

        assert received == []

    asyncio.run(scenario())


def test_cancel_after_the_player_is_already_matched_is_a_safe_no_op():
    async def scenario():
        bus = EventBus()
        received = []
        bus.subscribe(MatchFoundEvent, received.append)
        queue = _queue(bus, timeout_seconds=1.0)

        task = asyncio.ensure_future(queue.enqueue("alice", 1000))
        await asyncio.sleep(0)

        await queue.enqueue("bob", 1000)  # matches alice immediately
        await task

        # alice is already matched and gone from the queue - a late
        # CancelPlayRequest for her must not raise, and must not undo or
        # duplicate the match that already happened.
        assert queue.cancel("alice") is False
        assert received == [MatchFoundEvent(white_username="alice", black_username="bob")]

    asyncio.run(scenario())