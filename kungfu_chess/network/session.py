"""
session.py: tracks connections and assigns each one a role
(WHITE/BLACK/SPECTATOR), plus (as of feature/home-screen-basic-login) a
username. SessionManager does not know GameEngine, RuleEngine, or any
move legality - only "who is this connection and what role do they
have" in the narrowest sense. Connecting a Session's role to actual game
state (does GameEngine agree a move from this color is legal right now)
is game_session.py's job.

WHY register_connection() AND complete_login() ARE TWO SEPARATE STEPS
(split in feature/home-screen-basic-login, Step 3):
A raw WebSocket connection and an *identified* one are no longer the
same moment - a client now sends a LoginRequest(username) before it is
allowed to do anything else (see login_gate.py), and role assignment
must follow *login* order, not raw TCP-accept order, so that a client
that's slow to log in doesn't unfairly claim White just because its
socket connected microseconds earlier (see this branch's own test:
"second to connect, first to log in, gets White"). register_connection()
therefore creates a role-less (pending) Session the instant a socket
connects; complete_login() is the only thing that ever assigns a role,
called once a LoginRequest actually arrives.

WHY A FREED COLOR GOES TO THE NEXT *NEW* LOGIN, NOT AN EXISTING
SPECTATOR (no auto-promotion):
Deliberate scope decision, unchanged from before this split: promoting
an already-connected spectator into an empty player slot needs its own
policy (which spectator, does the game reset or resume) that belongs
with reconnect/matchmaking handling in a later layer
(feature/matchmaking-disconnect), not here. SessionManager only ever
looks at "is 'w' or 'b' currently taken", so a freed color is picked up
by whichever connection *logs in* next, spectator-already-connected or
not - there is no promotion path at all.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, Optional


class PlayerRole(Enum):
    WHITE = auto()
    BLACK = auto()
    SPECTATOR = auto()


_ROLE_TO_COLOR = {PlayerRole.WHITE: "w", PlayerRole.BLACK: "b"}


@dataclass
class Session:
    connection: Any
    role: Optional[PlayerRole]  # None until complete_login() assigns one
    connected_at: datetime
    username: Optional[str] = None

    @property
    def color(self) -> Optional[str]:
        """'w' / 'b' for an assigned player, None for a spectator OR a
        connection that hasn't logged in yet."""
        return _ROLE_TO_COLOR.get(self.role) if self.role is not None else None

    @property
    def is_logged_in(self) -> bool:
        return self.role is not None


class SessionManager:
    def __init__(self):
        self._sessions: Dict[Any, Session] = {}
        self._role_taken = {PlayerRole.WHITE: False, PlayerRole.BLACK: False}

    def register_connection(self, connection: Any) -> Session:
        """A socket just connected - no role yet, no username yet."""
        session = Session(connection=connection, role=None, connected_at=datetime.now(timezone.utc))
        self._sessions[connection] = session
        return session

    def complete_login(self, connection: Any, username: str) -> Session:
        """A LoginRequest just arrived for an already-registered
        connection. Assigns the role by *login* order - whichever
        connection calls this first gets WHITE, regardless of which one
        connected first at the TCP level."""
        session = self._sessions[connection]

        if not self._role_taken[PlayerRole.WHITE]:
            role = PlayerRole.WHITE
        elif not self._role_taken[PlayerRole.BLACK]:
            role = PlayerRole.BLACK
        else:
            role = PlayerRole.SPECTATOR

        if role is not PlayerRole.SPECTATOR:
            self._role_taken[role] = True

        session.role = role
        session.username = username
        return session

    def unregister_connection(self, connection: Any) -> None:
        session = self._sessions.pop(connection, None)
        if session is not None and session.role in (PlayerRole.WHITE, PlayerRole.BLACK):
            self._role_taken[session.role] = False