"""
BoardParser: turns the textual board notation ("wK . bR" rows) into a
real Board populated with Piece objects.

WHY THIS LIVES IN kungfu_chess/io/, NOT INSIDE texttests/:
Section 13 of the design guide calls this out explicitly as a named
mistake to avoid ("Hiding BoardParser inside texttests"): the *shipped
application* also needs to load a starting position from text, not only
the test runner. If BoardParser lived inside texttests, the app would
either duplicate parsing logic or depend on the test package - both
wrong. Living in io/ means both app.py and texttests/script_runner.py
import the same adapter and are guaranteed to agree on what a given board
string means.

WHY VALIDATION RAISES A TYPED EXCEPTION INSTEAD OF RETURNING None/error-code:
Parsing happens once, at the start of a game or a script - it's not a
per-frame hot path where exceptions would be expensive, and a malformed
board is a *programming/authoring* error (bad test fixture, bad save
file), not an expected runtime outcome the caller should have to check
for on every call. `BoardParseError` with a stable `.reason` still gives
tests a stable string to assert on (same "reason code" idea as
MoveValidation/MoveResult), while letting callers that don't expect bad
input skip a manual `if error: ...` check.

WHY PIECE IDS ARE ASSIGNED HERE, SEQUENTIALLY, IN READING ORDER:
Section 6: "Piece IDs are assigned consistently at creation time, either
by BoardParser or by a dedicated PieceFactory." Doing it here (rather
than a separate factory) keeps id-assignment next to the only place that
already walks every cell in a fixed, deterministic order - reading order
also makes test fixtures reproducible: parsing the same board text twice
always assigns the same ids to the same pieces, which matters for text
integration tests that print pieces or reason about "the same piece" step
to step.
"""

from typing import List

from kungfu_chess.model.position import Position
from kungfu_chess.model.piece import Piece
from kungfu_chess.model.board import Board
import kungfu_chess.config as config


class BoardParseError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class BoardParser:
    def parse(self, rows: List[List[str]]) -> Board:
        if not rows:
            raise BoardParseError("empty_board")

        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise BoardParseError("row_width_mismatch")

        board = Board(width=width, height=len(rows))
        next_id = 1

        for r, row in enumerate(rows):
            for c, token in enumerate(row):
                if token == '.':
                    continue
                self._validate_token(token)
                board.add_piece(Piece(
                    id=next_id,
                    color=token[0],
                    kind=token[1],
                    cell=Position(r, c),
                ))
                next_id += 1

        return board

    def _validate_token(self, token: str) -> None:
        if (
            len(token) != 2
            or token[0] not in config.VALID_COLORS
            or token[1] not in config.VALID_KINDS
        ):
            raise BoardParseError("unknown_token")
