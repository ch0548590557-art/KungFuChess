"""
protocol: the wire message shapes exchanged between a WS client and the
WebSocketServer, plus JSON encode/decode for them. See docs/ws_protocol.md
for the human-readable schema this module implements.

This module knows nothing about GameEngine, GameSession, or the network
transport itself - only the message shapes and how to turn them into/out
of JSON text. Game logic (deciding whether a MoveRequest is legal, who is
allowed to send one) belongs in game_session.py, which imports this
module rather than the other way around.

WHY A "type" DISCRIMINATOR FIELD RATHER THAN FOUR SEPARATE JSON SHAPES
WITH NO COMMON ENVELOPE:
A single JSON object per message, tagged with its own class name, lets a
receiver dispatch on one field (`payload["type"]`) before it knows
anything else about the message - the alternative (guessing the type
from which fields are present) would make MoveRequest and JumpRequest
ambiguous, since both could plausibly omit a `destination`.

WHY GameStateUpdate's pieces/motions/captures/completed_moves ARE LISTS
OF DEDICATED DATACLASSES (PieceInfo/MotionInfo/CaptureInfo/CompletedMove)
RATHER THAN RAW LISTS/TUPLES:
GameEngine.snapshot() itself represents these as plain tuples (Section
9's GameSnapshot is an internal, same-process value object with no wire
concerns). Copying that shape verbatim onto the network protocol would
mean every field is accessed by position (`piece[2]` for row) instead of
by name, and a typo in field order would only surface as a runtime KeyError
in a client written months later. A dedicated dataclass per row-shape
costs a bit more code here but makes every field named and gives static
type checkers something to check at both encode and decode time.

WHY GameStateUpdate.your_color EXISTS EVEN THOUGH IT WASN'T IN THE
ORIGINAL FOUR-MESSAGE LIST:
Nothing else in this protocol ever tells a client which color (or
spectator status) it was assigned - GameStateUpdate is the only message
type broadcast to clients, so this field rides along on it rather than
inventing a fifth message type for one piece of per-recipient
information. Two clients receiving the "same" GameStateUpdate broadcast
therefore actually receive two personalized copies, differing only in
this field - see game_session.py's per-connection broadcast.

WHY MoveRequest/JumpRequest/MotionInfo CARRY Position OBJECTS AND NOT
(row, col) TUPLES:
Position already exists as the project's value type for a board cell
(model/position.py) - reusing it here means the network layer speaks the
same vocabulary as GameEngine.request_move()/request_jump() instead of
inventing a parallel (row, col) convention that would need translating
at the boundary either way.
"""

import json
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Union

from kungfu_chess.model.position import Position


@dataclass
class MoveRequest:
    source: Position
    destination: Position


@dataclass
class JumpRequest:
    source: Position


@dataclass
class PieceInfo:
    kind: str
    color: str
    row: int
    col: int
    state: str  # PieceState member name, e.g. "IDLE" - see model/piece.py


@dataclass
class MotionInfo:
    source: Position
    destination: Position
    start_time_ms: int
    arrival_time_ms: int


@dataclass
class CaptureInfo:
    kind: str
    color: str  # color of the captured piece


@dataclass
class CompletedMove:
    color: str
    san: str
    timestamp_ms: int


@dataclass
class GameStateUpdate:
    board_width: int
    board_height: int
    pieces: List[PieceInfo]
    game_over: bool
    winner: Optional[str] = None
    motions: List[MotionInfo] = field(default_factory=list)
    captures: List[CaptureInfo] = field(default_factory=list)
    completed_moves: List[CompletedMove] = field(default_factory=list)
    your_color: Optional[str] = None  # "w" | "b" | None (spectator) - see module docstring

    @staticmethod
    def from_snapshot(snapshot, your_color: Optional[str] = None) -> "GameStateUpdate":
        pieces = [
            PieceInfo(kind=kind, color=color, row=row, col=col, state=state)
            for kind, color, row, col, state in snapshot.pieces
        ]
        motions = [
            MotionInfo(
                source=Position(src_row, src_col),
                destination=Position(dst_row, dst_col),
                start_time_ms=start_ms,
                arrival_time_ms=arrival_ms,
            )
            for (src_row, src_col), (dst_row, dst_col, start_ms, arrival_ms)
            in snapshot.motions.items()
        ]
        captures = [CaptureInfo(kind=kind, color=color) for kind, color in snapshot.captures]
        completed_moves = [
            CompletedMove(color=color, san=san, timestamp_ms=timestamp_ms)
            for color, san, timestamp_ms in snapshot.completed_moves
        ]
        return GameStateUpdate(
            board_width=snapshot.board_width,
            board_height=snapshot.board_height,
            pieces=pieces,
            game_over=snapshot.game_over,
            winner=snapshot.winner,
            motions=motions,
            captures=captures,
            completed_moves=completed_moves,
            your_color=your_color,
        )


@dataclass
class Error:
    reason: str


Message = Union[MoveRequest, JumpRequest, GameStateUpdate, Error]

_TYPE_NAMES = {
    MoveRequest: "move_request",
    JumpRequest: "jump_request",
    GameStateUpdate: "game_state_update",
    Error: "error",
}
_NAMES_TO_TYPE = {name: cls for cls, name in _TYPE_NAMES.items()}


def encode(message: Message) -> str:
    payload = asdict(message)
    payload["type"] = _TYPE_NAMES[type(message)]
    return json.dumps(payload)


def decode(raw: str) -> Message:
    payload = json.loads(raw)
    msg_type = payload.pop("type", None)
    cls = _NAMES_TO_TYPE.get(msg_type)
    if cls is None:
        raise ValueError(f"unknown message type: {msg_type!r}")

    if cls is MoveRequest:
        return MoveRequest(
            source=Position(**payload["source"]),
            destination=Position(**payload["destination"]),
        )
    if cls is JumpRequest:
        return JumpRequest(source=Position(**payload["source"]))
    if cls is GameStateUpdate:
        return GameStateUpdate(
            board_width=payload["board_width"],
            board_height=payload["board_height"],
            pieces=[PieceInfo(**p) for p in payload["pieces"]],
            game_over=payload["game_over"],
            winner=payload.get("winner"),
            motions=[
                MotionInfo(
                    source=Position(**m["source"]),
                    destination=Position(**m["destination"]),
                    start_time_ms=m["start_time_ms"],
                    arrival_time_ms=m["arrival_time_ms"],
                )
                for m in payload.get("motions", [])
            ],
            captures=[CaptureInfo(**c) for c in payload.get("captures", [])],
            completed_moves=[CompletedMove(**cm) for cm in payload.get("completed_moves", [])],
            your_color=payload.get("your_color"),
        )
    return cls(**payload)  # Error