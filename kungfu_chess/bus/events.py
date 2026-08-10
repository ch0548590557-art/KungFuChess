"""
Event dataclasses carried on the EventBus. Each one is a plain, inert
value object - no behavior, no reference back to the component that
published it - so publishers and subscribers only ever need to share
these shapes, never each other's concrete classes.

WHY FrameTickEvent.snapshot IS TYPED Any INSTEAD OF GameSnapshot:
Importing GameSnapshot here would couple the bus package (meant to sit
below every other package) to engine/game_engine.py. The bus stays a
leaf dependency; callers that need the real shape already import
GameSnapshot themselves.
"""

from dataclasses import dataclass
from typing import Any

from kungfu_chess.model.position import Position


@dataclass
class MouseClickEvent:
    x: int
    y: int


@dataclass
class MouseJumpEvent:
    x: int
    y: int


@dataclass
class MoveRequestedEvent:
    source: Position
    destination: Position


@dataclass
class JumpRequestedEvent:
    source: Position


@dataclass
class MoveCompletedEvent:
    source: Position
    destination: Position
    is_jump: bool = False


@dataclass
class FrameTickEvent:
    snapshot: Any  # engine.game_engine.GameSnapshot
    now_ms: int


@dataclass
class GameEndedEvent:
    """Published once, the moment a game ends - see game_engine.py's
    wait() for why this fires from the exact same spot GameState.game_over/
    winner get set. winner_color is 'w'/'b' ('w' won, or vice versa);
    reason is a stable code (currently only "king_captured" - see
    game_engine.py for why resignation isn't implemented yet)."""
    winner_color: str
    reason: str


@dataclass
class MatchFoundEvent:
    """Published once by MatchmakingQueue (matchmaking/matchmaking_queue.py)
    the moment it pairs two waiting players - the queue's only way of
    talking to whatever assigns roles/starts a game (SessionManager, Step 2
    of feature/matchmaking-disconnect), since the queue is deliberately kept
    ignorant of SessionManager/GameSession/networking (same reasoning as
    MoveCompletedEvent/GameEndedEvent above: publisher and subscriber only
    ever need to agree on this shape, not on each other's concrete classes).

    white_username/black_username are already color-assigned by the queue
    itself (whoever had been waiting longer becomes White - see
    matchmaking_queue.py's module docstring), not raw "player_a/player_b" -
    there is nothing left for a subscriber to decide about who plays which
    color, only who to hand those colors to."""
    white_username: str
    black_username: str
