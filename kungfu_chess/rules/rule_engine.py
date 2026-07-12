"""
RuleEngine answers exactly one question: "given source and destination,
is this command legal *right now*?" It never mutates Board and knows
nothing about game_over or in-flight motions (Section 8) - those are
application-level concerns that belong to GameEngine, one layer up.

WHY MoveValidation IS A DATACLASS INSTEAD OF A PLAIN (bool, str) TUPLE:
A tuple return value forces every caller to remember the *order*
(is_valid first? reason first?) and gives autocomplete nothing to work
with - `result[0]` reads as "the first thing", `result.is_valid` reads as
what it is. A dataclass also gives the result a name (MoveValidation) that
shows up in stack traces and test assertions, which matters a lot in a
course context where students are reading test failures (Section 2:
"make failure readable" is an explicit engineering habit).

WHY reason IS A STABLE STRING CODE ("outside_board", not a free-text
sentence):
Unit tests assert on `reason` (Section 8: "The DSL does not assert these
reasons. Unit tests assert them."). A free-text message like "That move
is not allowed because..." is prose meant for humans and is fragile to
assert on - reword it slightly and every test asserting the old wording
breaks. A short fixed vocabulary of reason codes is meant for tests and
for GameEngine (which sometimes needs to distinguish reasons
programmatically), while a human-facing message could be derived from the
code later if a UI needed one.

WHY VALIDATION ORDER IS FIXED (bounds -> empty source -> friendly
destination -> piece geometry):
Each check is cheap to explain and cheap to test in isolation, and
ordering cheapest/most-general checks first avoids doing expensive
geometry work (legal_destinations, which walks the board) for moves that
are already invalid for a simpler reason. It also keeps the reason
reported deterministic: a move that is *both* off-board and geometrically
illegal always reports "outside_board", never depends on set iteration
order.
"""

from dataclasses import dataclass

from kungfu_chess.model.position import Position
from kungfu_chess.model.board import Board
from kungfu_chess.rules.piece_rules import legal_destinations


@dataclass
class MoveValidation:
    is_valid: bool
    reason: str


class RuleEngine:
    def validate_move(self, board: Board, source: Position,
                       destination: Position) -> MoveValidation:
        if not board.in_bounds(source) or not board.in_bounds(destination):
            return MoveValidation(False, "outside_board")

        piece = board.piece_at(source)
        if piece is None:
            return MoveValidation(False, "empty_source")

        target = board.piece_at(destination)
        if target is not None and target.color == piece.color:
            return MoveValidation(False, "friendly_destination")

        if destination not in legal_destinations(board, piece):
            return MoveValidation(False, "illegal_piece_move")

        return MoveValidation(True, "ok")
