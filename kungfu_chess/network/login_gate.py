"""
login_gate: waits for a connection's first message to be a LoginRequest
or RegisterRequest, within a bounded time window, checks it against the
real AuthService, and returns the authenticated username - before
anything else is allowed to happen on that connection.

WHY THIS IS ITS OWN MODULE, INDEPENDENT OF GameSession/SessionManager
AND ws_server.py's CONNECTION-HANDLING LOOP:
"The client must identify itself within N seconds or the connection is
dropped" is a pure transport/timing concern with nothing chess-specific
about it - GameSession only needs to know *that* a username arrived, not
how long the server was willing to wait or what counts as a malformed
first message. Keeping it separate is what let this module absorb real
authentication (feature/auth-sqlite-elo, Step 4) as a change *inside*
await_login() - AuthService lookups replaced the placeholder
"any username is fine" acceptance - without GameSession or the
waiting/timeout/malformed-input handling around it needing to change at
all.

WHY THREE DISTINCT EXCEPTIONS (LoginTimeout vs LoginFailed vs the
AuthService exceptions caught and re-raised as LoginFailed) INSTEAD OF
ONE:
A client that never sends anything (timeout), one that sends garbage or
the wrong message type (malformed/wrong-type failure), and one that
sends a well-formed but rejected RegisterRequest/LoginRequest
(username_taken/invalid_credentials) are different failure modes with
different Error reasons for the caller to report - collapsing them would
throw away information a client UI needs to explain what actually went
wrong. AuthService's own exceptions (UsernameTakenError/
InvalidCredentialsError) are caught here and re-raised as LoginFailed so
ws_server.py only ever needs to catch LoginTimeout/LoginFailed, never an
AuthService-specific type.

WHY RegisterRequest AND LoginRequest ARE HANDLED IN THE SAME await_login()
RATHER THAN TWO SEPARATE GATE FUNCTIONS:
Both are "the connection's very first message, within the same timeout
window, producing the same result (an authenticated username) or the
same family of failures" - the only difference is which AuthService
method to call. Splitting that into two functions would duplicate the
timeout/decode/error-translation plumbing for a difference of one method
call.
"""

import asyncio

from kungfu_chess.auth.auth_service import AuthService, InvalidCredentialsError, UsernameTakenError
from kungfu_chess.network import protocol

DEFAULT_LOGIN_TIMEOUT_SECONDS = 5.0


class LoginTimeout(Exception):
    """No message arrived at all within the timeout window."""


class LoginFailed(Exception):
    """A message arrived, but it wasn't accepted - malformed JSON, an
    unrecognized type, a recognized-but-wrong type (e.g. a MoveRequest
    sent before logging in), or a well-formed RegisterRequest/LoginRequest
    that AuthService rejected (username_taken/invalid_credentials)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


async def await_login(
    websocket, auth_service: AuthService,
    timeout_seconds: float = DEFAULT_LOGIN_TIMEOUT_SECONDS,
) -> str:
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

    if isinstance(message, protocol.RegisterRequest):
        try:
            user = auth_service.register(message.username, message.password)
        except UsernameTakenError as exc:
            raise LoginFailed(exc.reason) from exc
    elif isinstance(message, protocol.LoginRequest):
        try:
            user = auth_service.authenticate(message.username, message.password)
        except InvalidCredentialsError as exc:
            raise LoginFailed(exc.reason) from exc
    else:
        raise LoginFailed("login_required")

    return user.username