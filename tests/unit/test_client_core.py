import pytest

from kungfu_chess.model.position import Position
from kungfu_chess.network import protocol
from kungfu_chess.network.client_core import ClientCore, SentRequest
from kungfu_chess.network.login_prompt import LoginPrompt


def _update(your_color=None):
    return protocol.GameStateUpdate(
        board_width=8, board_height=8, pieces=[], game_over=False,
        your_color=your_color,
    )


def test_dispatch_routes_state_updates_and_errors_independent_of_order():
    client = ClientCore("ws://unused")
    states = []
    errors = []
    client.on_state_update(states.append)
    client.on_error(lambda error, request: errors.append(error))

    # Simulate exactly the race documented in docs/ws_protocol.md: an
    # unrelated tick broadcast arrives before the direct Error reply to
    # a request this client sent.
    client._dispatch(_update(your_color="w"))
    client._dispatch(protocol.Error(reason="illegal_piece_move"))
    client._dispatch(_update(your_color="w"))

    assert len(states) == 2
    assert errors == [protocol.Error(reason="illegal_piece_move")]


def test_last_state_and_my_color_are_cached_from_the_most_recent_update():
    client = ClientCore("ws://unused")
    client._dispatch(_update(your_color="b"))

    assert client.my_color == "b"
    assert client.last_state.your_color == "b"


def test_last_error_is_cached():
    client = ClientCore("ws://unused")
    client._dispatch(protocol.Error(reason="wrong_color"))

    assert client.last_error == protocol.Error(reason="wrong_color")


def test_dispatch_without_registered_handlers_does_not_raise():
    client = ClientCore("ws://unused")
    client._dispatch(_update())  # must not raise
    client._dispatch(protocol.Error(reason="x"))  # must not raise


def test_error_with_unknown_request_id_still_calls_the_handler_with_no_request():
    """A request_id the client never sent (defensive case - shouldn't
    happen from our own ClientCore, which always encodes a valid request,
    but a malformed/foreign message could carry one)."""
    client = ClientCore("ws://unused")
    seen = []
    client.on_error(lambda error, request: seen.append((error, request)))

    client._dispatch(protocol.Error(reason="wrong_color", request_id="never-sent"))

    assert seen == [(protocol.Error(reason="wrong_color", request_id="never-sent"), None)]


def test_error_with_no_request_id_still_calls_the_handler_with_no_request():
    """The server sends request_id=None for malformed_message/
    unknown_message_type (it couldn't recover the id at all) - the
    handler must still fire, just without a matched SentRequest."""
    client = ClientCore("ws://unused")
    seen = []
    client.on_error(lambda error, request: seen.append((error, request)))

    client._dispatch(protocol.Error(reason="malformed_message", request_id=None))

    assert seen == [(protocol.Error(reason="malformed_message", request_id=None), None)]


def test_error_matching_a_pending_request_id_is_correlated_and_popped():
    client = ClientCore("ws://unused")
    pending = SentRequest(
        request_id="5", kind="move", source=Position(6, 4), destination=Position(4, 4),
    )
    client._pending_requests["5"] = pending
    seen = []
    client.on_error(lambda error, request: seen.append((error, request)))

    client._dispatch(protocol.Error(reason="illegal_piece_move", request_id="5"))

    assert seen == [(protocol.Error(reason="illegal_piece_move", request_id="5"), pending)]
    assert "5" not in client._pending_requests


class _FakeLoginPrompt(LoginPrompt):
    def __init__(self, username: str):
        self._username = username

    def get_username(self) -> str:
        return self._username


def test_prepare_login_stores_and_returns_the_username():
    client = ClientCore("ws://unused", login_prompt=_FakeLoginPrompt("chani"))

    result = client.prepare_login()

    assert result == "chani"
    assert client.username == "chani"


def test_prepare_login_without_a_login_prompt_raises():
    client = ClientCore("ws://unused")

    with pytest.raises(RuntimeError):
        client.prepare_login()


def test_prepare_login_never_calls_anything_but_get_username():
    """ClientCore must only ever call get_username() on the injected
    LoginPrompt - it has no business knowing anything else about it
    (e.g. that it's shell-based)."""

    class _StrictLoginPrompt(LoginPrompt):
        def get_username(self) -> str:
            return "chani"

        def __getattr__(self, name):
            raise AssertionError(f"ClientCore touched unexpected attribute: {name}")

    client = ClientCore("ws://unused", login_prompt=_StrictLoginPrompt())
    assert client.prepare_login() == "chani"