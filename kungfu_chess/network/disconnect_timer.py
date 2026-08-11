"""
disconnect_timer: waits, for a bounded time window, for a disconnected
player to reconnect - before anything else (auto-resign, Step 4) is
allowed to happen to their Session.

WHY THIS IS ITS OWN MODULE, INDEPENDENT OF SessionManager/GameSession/
ws_server.py's CONNECTION-HANDLING LOOP:
Deliberately the exact same shape as login_gate.py's await_login(), for
the exact same reason: "wait up to N seconds for something to happen,
or give up" is a pure transport/timing concern with nothing chess- or
session-specific about it - SessionManager already owns *marking* a
session DISCONNECTED (see session.py's unregister_connection()); this
module only owns the *waiting*. Keeping it separate is what lets Step 4
(auto-resign on timeout) and Step 5 (reconnect - session.reconnected.set())
land as changes around this function rather than inside it.

WHY await_reconnect_or_timeout() TAKES A PLAIN asyncio.Event RATHER THAN
A Session:
The only thing this function needs is something that can be waited on
and something that can be set from elsewhere - Session.reconnected (see
session.py) already is exactly that. Taking the bare Event instead of
the whole Session keeps this module ignorant of PlayerRole/SessionState/
usernames entirely, matching login_gate.py's own ignorance of
SessionManager - it only ever deals in "wait for this signal or time
out", the same way await_login() only ever deals in "wait for this
message or time out".

WHY THIS RAISES ReconnectTimeout INSTEAD OF LETTING asyncio.TimeoutError
PROPAGATE:
Same reasoning as login_gate.LoginTimeout: a project-specific exception
type lets a caller (ws_server.py) catch exactly "the wait we asked for
expired" without also accidentally catching an unrelated TimeoutError
raised by something else nested inside the same await.
"""

import asyncio

DEFAULT_DISCONNECT_TIMEOUT_SECONDS = 20.0


class ReconnectTimeout(Exception):
    """No reconnect (session.reconnected.set()) arrived within the
    timeout window - as of Step 3, nothing sets reconnected yet (that's
    Step 5), so every disconnect timer today resolves via this branch."""


async def await_reconnect_or_timeout(
    reconnected: asyncio.Event,
    timeout_seconds: float = DEFAULT_DISCONNECT_TIMEOUT_SECONDS,
) -> None:
    """Blocks until either `reconnected` is set (returns normally) or
    timeout_seconds elapses (raises ReconnectTimeout)."""
    try:
        await asyncio.wait_for(reconnected.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise ReconnectTimeout()