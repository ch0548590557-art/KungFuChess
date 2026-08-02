"""
login_gate: waits for a connection's first message to be a LoginRequest,
within a bounded time window, before anything else is allowed to happen
on that connection.

WHY THIS IS ITS OWN MODULE, INDEPENDENT OF GameSession/SessionManager
AND ws_server.py's CONNECTION-HANDLING LOOP:
"The client must identify itself within N seconds or the connection is
dropped" is a pure transport/timing concern with nothing chess-specific
about it - GameSession only needs to know *that* a username arrived, not
how long the server was willing to wait or what counts as a malformed
first message. Keeping it separate means this exact mechanism can be
reused almost unchanged when this becomes a real authentication gate
(feature/auth-sqlite-elo): only what happens *after* a successful
identification (password check, DB lookup) changes, not the
waiting/timeout/malformed-input handling itself.

WHY TWO DISTINCT EXCEPTIONS (LoginTimeout vs LoginFailed) INSTEAD OF ONE:
A client that never sends anything (timeout) and a client that sends
garbage or the wrong message type (failed) are different failure modes
with different Error reasons for the caller to report
("login_timeout" vs whatever LoginFailed.reason carries) - collapsing
them would throw away information a client UI needs to explain what
actually went wrong.
"""

import asyncio

from kungfu_chess.network import protocol

DEFAULT_LOGIN_TIMEOUT_SECONDS = 5.0


class LoginTimeout(Exception):
    """No message arrived at all within the timeout window."""


class LoginFailed(Exception):
    """A message arrived, but it wasn't a well-formed LoginRequest -
    malformed JSON, an unrecognized type, or a recognized-but-wrong
    type (e.g. a MoveRequest sent before logging in)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


async def await_login(
    websocket, timeout_seconds: float = DEFAULT_LOGIN_TIMEOUT_SECONDS,
) -> protocol.LoginRequest:
    try:
        raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise LoginTimeout()

    try:
        message = protocol.decode(raw)
    except protocol.UnknownMessageType:
        raise LoginFailed("unknown_message_type")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise LoginFailed("malformed_message")

    if not isinstance(message, protocol.LoginRequest):
        raise LoginFailed("login_required")

    return message