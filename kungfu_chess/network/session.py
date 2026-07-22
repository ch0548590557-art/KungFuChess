"""
session.py: assigns a role (WHITE/BLACK/SPECTATOR) to each WS connection
by arrival order, and nothing else. Per fix/complete-ws-transport-layer's
step 2: SessionManager does not know GameEngine, RuleEngine, or any move
legality - only "who is this connection and what role do they have" in
the narrowest sense. Connecting a Session's role to actual game state
(does GameEngine agree a move from this color is legal right now) is
Step 3's job, in game_session.py.

WHY A FREED COLOR GOES TO THE NEXT *NEW* CONNECTION, NOT AN EXISTING
SPECTATOR (no auto-promotion):
Deliberate scope decision for this branch (2026-07-22): promoting an
already-connected spectator into an empty player slot needs its own
policy (which spectator, does the game reset or resume) that belongs
with reconnect/matchmaking handling in a later layer
(feature/matchmaking-disconnect, alongside auto-resign/timers), not
here. SessionManager only ever looks at "is 'w' or 'b' currently taken",
so a freed color is picked up by whichever connection registers next,
spectator-already-connected or not - there is no promotion path at all.
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
    role: PlayerRole
    connected_at: datetime

    @property
    def color(self) -> Optional[str]:
        """'w' / 'b' for an assigned player, None for a spectator."""
        return _ROLE_TO_COLOR.get(self.role)


class SessionManager:
    def __init__(self):
        self._sessions: Dict[Any, Session] = {}
        self._role_taken = {PlayerRole.WHITE: False, PlayerRole.BLACK: False}

    def register_connection(self, connection: Any) -> Session:
        if not self._role_taken[PlayerRole.WHITE]:
            role = PlayerRole.WHITE
        elif not self._role_taken[PlayerRole.BLACK]:
            role = PlayerRole.BLACK
        else:
            role = PlayerRole.SPECTATOR

        if role is not PlayerRole.SPECTATOR:
            self._role_taken[role] = True

        session = Session(connection=connection, role=role, connected_at=datetime.now(timezone.utc))
        self._sessions[connection] = session
        return session

    def unregister_connection(self, connection: Any) -> None:
        session = self._sessions.pop(connection, None)
        if session is not None and session.role is not PlayerRole.SPECTATOR:
            self._role_taken[session.role] = False