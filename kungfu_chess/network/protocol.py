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

WHY MoveRequest/JumpRequest CARRY A request_id (ADDED IN STEP 4):
ClientCore's send_move()/send_jump() are fire-and-forget (no ack for an
accepted request - see game_session.py, which only ever produces a
direct reply for a *rejected* one). Without something identifying which
request an Error is about, a client that has more than one request in
flight at once (e.g. a double-click before the first resolves) cannot
tell which of its requests was rejected - "one of your recent requests
failed: reason=X" is not actionable. request_id (any client-chosen
string; ClientCore uses a local incrementing counter) makes that
determinable: GameSession only ever echoes it back verbatim onto the
Error it returns to that same sender, never interprets it. GameStateUpdate
does not get one - it is never a reply to a specific request, only a
broadcast (see your_color's docstring above for the same reasoning).

WHY LoginRequest EXISTS (feature/home-screen-basic-login):
A client now sends its chosen username right after connecting, before
any MoveRequest/JumpRequest - a *placeholder* identity step (no
password, no DB, no real authentication yet). It carries no request_id:
it isn't a game action GameEngine could accept/reject, and there is
nothing new for the server to reply with - role assignment still rides
on GameStateUpdate.your_color exactly as before. A later step in this
same branch changes *when* that assignment happens (by login order
rather than raw connection order), but doesn't add a dedicated login
reply message.

WHY GameStateUpdate CARRIES white_username/black_username (feature/
home-screen-basic-login, added after login-order role assignment
shipped):
A client learns its *own* color from your_color, but has no way to
know who it's playing against - LoginRequest only ever travels
client->server, so a client never sees the other side's username over
the wire any other way. Both fields default to None (nobody has logged
in as that color yet, e.g. right after the first player connects) and
are broadcast identically to every recipient (unlike your_color, which
is personalized per connection) - "who is White" is the same fact for
everyone watching, not something that varies by who's asking.
"""

import json
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Union

from kungfu_chess.model.position import Position


@dataclass
class MoveRequest:
    request_id: str
    source: Position
    destination: Position


@dataclass
class JumpRequest:
    request_id: str
    source: Position


@dataclass
class LoginRequest:
    username: str


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
    white_username: Optional[str] = None  # None until someone has logged in as White
    black_username: Optional[str] = None  # None until someone has logged in as Black

    @staticmethod
    def from_snapshot(
        snapshot, your_color: Optional[str] = None,
        white_username: Optional[str] = None, black_username: Optional[str] = None,
    ) -> "GameStateUpdate":
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
            white_username=white_username,
            black_username=black_username,
        )


@dataclass
class Error:
    reason: str
    request_id: Optional[str] = None  # echoed from the request that caused it, when known


class UnknownMessageType(ValueError):
    """Raised by decode() specifically when payload["type"] doesn't match
    any known message type - narrower than a malformed/incomplete payload
    for an otherwise-recognized type, so a caller (GameSession) can tell
    the two apart and report the distinct Error reasons documented in
    docs/ws_protocol.md (unknown_message_type vs malformed_message).
    Subclasses ValueError so existing `except ValueError` callers still
    catch it without changes."""


Message = Union[MoveRequest, JumpRequest, LoginRequest, GameStateUpdate, Error]

_TYPE_NAMES = {
    MoveRequest: "move_request",
    JumpRequest: "jump_request",
    LoginRequest: "login_request",
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
        raise UnknownMessageType(f"unknown message type: {msg_type!r}")

    if cls is MoveRequest:
        return MoveRequest(
            request_id=payload["request_id"],
            source=Position(**payload["source"]),
            destination=Position(**payload["destination"]),
        )
    if cls is JumpRequest:
        return JumpRequest(
            request_id=payload["request_id"],
            source=Position(**payload["source"]),
        )
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
            white_username=payload.get("white_username"),
            black_username=payload.get("black_username"),
        )
    return cls(**payload)  # Error or LoginRequest - both are flat, no nested Position fields