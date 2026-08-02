import asyncio

import pytest

from kungfu_chess.model.position import Position
from kungfu_chess.network import login_gate, protocol


class _FakeWebSocket:
    def __init__(self, raw_message=None, delay: float = 0.0):
        self._raw_message = raw_message
        self._delay = delay

    async def recv(self):
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._raw_message


def test_await_login_returns_the_login_request_on_success():
    async def scenario():
        raw = protocol.encode(protocol.LoginRequest(username="alice"))
        result = await login_gate.await_login(_FakeWebSocket(raw), timeout_seconds=1.0)
        assert result == protocol.LoginRequest(username="alice")

    asyncio.run(scenario())


def test_await_login_times_out_if_nothing_arrives():
    async def scenario():
        websocket = _FakeWebSocket(delay=10.0)  # much longer than the timeout below
        with pytest.raises(login_gate.LoginTimeout):
            await login_gate.await_login(websocket, timeout_seconds=0.05)

    asyncio.run(scenario())


def test_await_login_rejects_malformed_json():
    async def scenario():
        websocket = _FakeWebSocket("not json at all")
        with pytest.raises(login_gate.LoginFailed) as exc_info:
            await login_gate.await_login(websocket, timeout_seconds=1.0)
        assert exc_info.value.reason == "malformed_message"

    asyncio.run(scenario())


def test_await_login_rejects_unknown_message_type():
    async def scenario():
        websocket = _FakeWebSocket('{"type": "not_a_real_type"}')
        with pytest.raises(login_gate.LoginFailed) as exc_info:
            await login_gate.await_login(websocket, timeout_seconds=1.0)
        assert exc_info.value.reason == "unknown_message_type"

    asyncio.run(scenario())


def test_await_login_rejects_a_well_formed_non_login_message():
    async def scenario():
        move = protocol.encode(protocol.MoveRequest(
            request_id="1", source=Position(6, 4), destination=Position(4, 4),
        ))
        websocket = _FakeWebSocket(move)
        with pytest.raises(login_gate.LoginFailed) as exc_info:
            await login_gate.await_login(websocket, timeout_seconds=1.0)
        assert exc_info.value.reason == "login_required"

    asyncio.run(scenario())