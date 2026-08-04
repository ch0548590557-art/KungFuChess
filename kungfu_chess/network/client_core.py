"""
ClientCore: a minimal WS client for KungFuChess. Connects, sends
MoveRequest/JumpRequest, and dispatches every incoming message to a
registered callback by its type - never by "the next message is the
reply to what I just sent" (see docs/ws_protocol.md: "Message order is
not a reply contract" - the tick loop's broadcast and a direct reply to
one specific request race each other on the server side, as Step 3's
own integration tests discovered).

WHY prepare_login() IS ITS OWN METHOD RATHER THAN SOMETHING __init__
DOES AUTOMATICALLY (feature/home-screen-basic-login, Step 2):
Fetching credentials eagerly in __init__ would mean every existing
ClientCore(uri) construction site - including every test that never
cares about login - would suddenly block on a real LoginPrompt call.
A separate, explicitly-called method means login_prompt is accepted
(dependency injection, per this branch's own architecture note: the
only method ever called on it is get_credentials() - ClientCore has no
idea a terminal is involved) but nothing happens with it unless a
caller (repl_client.py) actually asks.

WHY connect() SENDS RegisterRequest/LoginRequest BEFORE WAITING FOR THE
WELCOME (feature/home-screen-basic-login Step 3; password + register/
login split added feature/auth-sqlite-elo Step 4):
The server now withholds everything - including the welcome
GameStateUpdate - until it receives a RegisterRequest or LoginRequest
(see ws_server.py and login_gate.py: role assignment is keyed on login
order, not raw TCP-accept order). connect() already blocks on
self._welcomed.wait() (see below); if it waited for that *before*
sending the login, every connection would deadlock instantly - the
server waiting on a login that never comes, the client waiting on a
welcome that never comes. Sending login right after opening the socket,
before ever awaiting the welcome, is what keeps this from being a
deadlock. connect() requires self.username and self._password to
already be set (call prepare_login() first) - there is nothing
meaningful to log in with otherwise. Which message type it sends
(RegisterRequest vs LoginRequest) follows whichever action the prompt
returned (self._login_action), stored verbatim from LoginCredentials.action
rather than re-derived.

WHY send_move()/send_jump() ARE FIRE-AND-FORGET, AND WHY THAT REQUIRES
request_id CORRELATION RATHER THAN JUST DOCUMENTING A "send one at a
time" DISCIPLINE:
An accepted request gets no direct reply at all (only the broadcast
GameStateUpdate already triggers on its own); only a *rejected* request
gets a direct Error. With more than one request in flight from the same
client at once (e.g. sent before the first resolved - a double-click,
or simply not waiting), a client needs to know *which* request an
incoming Error is about, not just that "one of them" failed - "one of
your recent requests was rejected" is not actionable. protocol.py's
request_id (Step 4 addition) solves this at the wire level: ClientCore
assigns a fresh id to every send, keeps a pending-request map, and
matches an incoming Error back to the SentRequest that caused it via
that id - GameSession only ever echoes the id, never interprets it.

WHY connect() BLOCKS UNTIL THE FIRST GameStateUpdate ARRIVES:
WebSocketServer always sends one immediately on a successful login so a
client learns its color without waiting for a tick. Awaiting it here
means `client.my_color` is already populated the moment connect()
returns, rather than forcing every caller to race the background listen
task themselves.
"""

import asyncio
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import websockets

from kungfu_chess.model.position import Position
from kungfu_chess.network import protocol
from kungfu_chess.network.login_prompt import LoginPrompt


@dataclass
class SentRequest:
    request_id: str
    kind: str  # "move" | "jump"
    source: Position
    destination: Optional[Position] = None


StateUpdateHandler = Callable[[protocol.GameStateUpdate], None]
ErrorHandler = Callable[[protocol.Error, Optional[SentRequest]], None]


class ClientCore:
    def __init__(self, uri: str, login_prompt: Optional[LoginPrompt] = None):
        self._uri = uri
        self._login_prompt = login_prompt
        self._connection = None
        self._listen_task = None
        self._welcomed = asyncio.Event()
        self._on_state_update: Optional[StateUpdateHandler] = None
        self._on_error: Optional[ErrorHandler] = None
        self._next_request_id = 0
        self._pending_requests: Dict[str, SentRequest] = {}
        self.last_state: Optional[protocol.GameStateUpdate] = None
        self.last_error: Optional[protocol.Error] = None
        self.username: Optional[str] = None
        self._password: Optional[str] = None
        self._login_action: str = "login"

    def prepare_login(self) -> str:
        """Collects credentials via the injected LoginPrompt and stores
        them (username, password, login-vs-register action). Must be
        called before connect() if a caller wants to log in at all (see
        repl_client.py) - nothing here talks to the network; sending
        credentials to the server is connect()'s job. Returns just the
        username, matching this method's pre-Step-4 signature - callers
        that only care about a display name (e.g. repl_client's
        "logging in as: ..." message) don't need to reach into private
        state for it."""
        if self._login_prompt is None:
            raise RuntimeError("prepare_login() called without a login_prompt")
        credentials = self._login_prompt.get_credentials()
        self.username = credentials.username
        self._password = credentials.password
        self._login_action = credentials.action
        return self.username

    @property
    def my_color(self) -> Optional[str]:
        """'w' / 'b' for an assigned player, None for a spectator (or if
        not connected yet)."""
        return self.last_state.your_color if self.last_state is not None else None

    def on_state_update(self, handler: StateUpdateHandler) -> None:
        self._on_state_update = handler

    def on_error(self, handler: ErrorHandler) -> None:
        self._on_error = handler

    async def connect(self) -> None:
        if self.username is None or self._password is None:
            raise RuntimeError("connect() called before prepare_login() - no credentials to log in with")
        self._connection = await websockets.connect(self._uri)
        self._listen_task = asyncio.ensure_future(self._listen())
        login_message = (
            protocol.RegisterRequest(username=self.username, password=self._password)
            if self._login_action == "register"
            else protocol.LoginRequest(username=self.username, password=self._password)
        )
        await self._connection.send(protocol.encode(login_message))
        await self._welcomed.wait()

    async def close(self) -> None:
        if self._listen_task is not None:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._connection is not None:
            await self._connection.close()

    async def send_move(self, source: Position, destination: Position) -> str:
        request_id = self._track(SentRequest(
            request_id=self._new_request_id(), kind="move",
            source=source, destination=destination,
        ))
        await self._connection.send(protocol.encode(
            protocol.MoveRequest(request_id=request_id, source=source, destination=destination)
        ))
        return request_id

    async def send_jump(self, source: Position) -> str:
        request_id = self._track(SentRequest(
            request_id=self._new_request_id(), kind="jump", source=source,
        ))
        await self._connection.send(protocol.encode(
            protocol.JumpRequest(request_id=request_id, source=source)
        ))
        return request_id

    def _new_request_id(self) -> str:
        self._next_request_id += 1
        return str(self._next_request_id)

    def _track(self, request: SentRequest) -> str:
        self._pending_requests[request.request_id] = request
        return request.request_id

    async def _listen(self) -> None:
        try:
            async for raw in self._connection:
                self._dispatch_raw(raw)
        except asyncio.CancelledError:
            pass
        except websockets.exceptions.ConnectionClosed:
            pass

    def _dispatch_raw(self, raw: str) -> None:
        try:
            message = protocol.decode(raw)
        except (ValueError, KeyError, TypeError, AttributeError):
            return
        self._dispatch(message)

    def _dispatch(self, message: protocol.Message) -> None:
        if isinstance(message, protocol.GameStateUpdate):
            self.last_state = message
            self._welcomed.set()
            if self._on_state_update is not None:
                self._on_state_update(message)
        elif isinstance(message, protocol.Error):
            self.last_error = message
            request = None
            if message.request_id is not None:
                request = self._pending_requests.pop(message.request_id, None)
            if self._on_error is not None:
                self._on_error(message, request)