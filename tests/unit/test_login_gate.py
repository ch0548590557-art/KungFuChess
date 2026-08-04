import asyncio

import pytest

from kungfu_chess.auth.auth_service import SqliteAuthService
from kungfu_chess.auth.sqlite_user_repository import SqliteUserRepository
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


def _auth_service() -> SqliteAuthService:
    return SqliteAuthService(SqliteUserRepository(":memory:"))


def test_await_login_registers_a_new_user_and_returns_the_username():
    async def scenario():
        auth = _auth_service()
        raw = protocol.encode(protocol.RegisterRequest(username="alice", password="hunter2"))
        result = await login_gate.await_login(_FakeWebSocket(raw), auth, timeout_seconds=1.0)
        assert result == "alice"
        assert auth.authenticate("alice", "hunter2").username == "alice"

    asyncio.run(scenario())


def test_await_login_authenticates_an_existing_user_and_returns_the_username():
    async def scenario():
        auth = _auth_service()
        auth.register("alice", "hunter2")
        raw = protocol.encode(protocol.LoginRequest(username="alice", password="hunter2"))
        result = await login_gate.await_login(_FakeWebSocket(raw), auth, timeout_seconds=1.0)
        assert result == "alice"

    asyncio.run(scenario())


def test_await_login_rejects_registering_a_taken_username():
    async def scenario():
        auth = _auth_service()
        auth.register("alice", "hunter2")
        raw = protocol.encode(protocol.RegisterRequest(username="alice", password="something else"))
        with pytest.raises(login_gate.LoginFailed) as exc_info:
            await login_gate.await_login(_FakeWebSocket(raw), auth, timeout_seconds=1.0)
        assert exc_info.value.reason == "username_taken"

    asyncio.run(scenario())


def test_await_login_rejects_login_with_wrong_password():
    async def scenario():
        auth = _auth_service()
        auth.register("alice", "hunter2")
        raw = protocol.encode(protocol.LoginRequest(username="alice", password="wrong"))
        with pytest.raises(login_gate.LoginFailed) as exc_info:
            await login_gate.await_login(_FakeWebSocket(raw), auth, timeout_seconds=1.0)
        assert exc_info.value.reason == "invalid_credentials"

    asyncio.run(scenario())


def test_await_login_rejects_login_for_unknown_username():
    async def scenario():
        auth = _auth_service()
        raw = protocol.encode(protocol.LoginRequest(username="nobody", password="anything"))
        with pytest.raises(login_gate.LoginFailed) as exc_info:
            await login_gate.await_login(_FakeWebSocket(raw), auth, timeout_seconds=1.0)
        assert exc_info.value.reason == "invalid_credentials"

    asyncio.run(scenario())


def test_await_login_times_out_if_nothing_arrives():
    async def scenario():
        websocket = _FakeWebSocket(delay=10.0)  # much longer than the timeout below
        with pytest.raises(login_gate.LoginTimeout):
            await login_gate.await_login(websocket, _auth_service(), timeout_seconds=0.05)

    asyncio.run(scenario())


def test_await_login_rejects_malformed_json():
    async def scenario():
        websocket = _FakeWebSocket("not json at all")
        with pytest.raises(login_gate.LoginFailed) as exc_info:
            await login_gate.await_login(websocket, _auth_service(), timeout_seconds=1.0)
        assert exc_info.value.reason == "malformed_message"

    asyncio.run(scenario())


def test_await_login_rejects_unknown_message_type():
    async def scenario():
        websocket = _FakeWebSocket('{"type": "not_a_real_type"}')
        with pytest.raises(login_gate.LoginFailed) as exc_info:
            await login_gate.await_login(websocket, _auth_service(), timeout_seconds=1.0)
        assert exc_info.value.reason == "unknown_message_type"

    asyncio.run(scenario())


def test_await_login_rejects_a_well_formed_non_login_message():
    async def scenario():
        move = protocol.encode(protocol.MoveRequest(
            request_id="1", source=Position(6, 4), destination=Position(4, 4),
        ))
        websocket = _FakeWebSocket(move)
        with pytest.raises(login_gate.LoginFailed) as exc_info:
            await login_gate.await_login(websocket, _auth_service(), timeout_seconds=1.0)
        assert exc_info.value.reason == "login_required"

    asyncio.run(scenario())