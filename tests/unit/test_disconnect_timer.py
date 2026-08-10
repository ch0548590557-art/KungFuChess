import asyncio

import pytest

from kungfu_chess.network import disconnect_timer


def test_await_reconnect_or_timeout_returns_normally_when_reconnected_is_set_in_time():
    async def scenario():
        reconnected = asyncio.Event()

        async def set_it_shortly():
            await asyncio.sleep(0.02)
            reconnected.set()

        asyncio.ensure_future(set_it_shortly())
        await disconnect_timer.await_reconnect_or_timeout(reconnected, timeout_seconds=1.0)  # must not raise

    asyncio.run(scenario())


def test_await_reconnect_or_timeout_raises_when_nothing_sets_reconnected():
    async def scenario():
        reconnected = asyncio.Event()
        with pytest.raises(disconnect_timer.ReconnectTimeout):
            await disconnect_timer.await_reconnect_or_timeout(reconnected, timeout_seconds=0.05)

    asyncio.run(scenario())