"""
notation.py: pure translation from one completed arrival's raw facts
(which piece moved, from where, to where, did it capture, did it
promote) into simplified algebraic chess notation.

WHY THIS REUSES piece_rules.legal_destinations FOR DISAMBIGUATION:
RuleEngine already treats legal_destinations() as the one source of
truth for "where can this piece go" (rules/piece_rules.py). SAN
disambiguation (Nbd7 vs Nfd7) is really the same question asked about a
*different* piece of the same kind/color - "could this other piece have
also legally reached the destination". Reusing the exact same function
means a notation bug can never disagree with what RuleEngine itself
considers legal; a second, hand-rolled "could this piece also get
there" check would be a second thing to keep in sync with piece_rules
forever.

SCOPE (deliberately, for now): this project's real-time "Kung Fu Chess"
has no check/checkmate/castling/en-passant rules implemented anywhere
yet (rule_engine.py / piece_rules.py have none of these) - so this never
emits +, #, O-O, O-O-O, or en-passant notation. Plain moves, captures,
and promotion only.

WHY _disambiguator TEMPORARILY MOVES `piece` BACK TO `source`:
By the time build_san() runs, `piece` has already arrived at
`destination` (Board only ever mutates on arrival, per motion.py's own
rationale). If a rival's legal_destinations() were evaluated against
that as-is, `destination` would always look same-color-occupied (by
`piece` itself) and every rival would always fail the check -
disambiguation could never trigger at all, for any move. Moving `piece`
back to `source` for the duration of the rivals check (then forward
again immediately after) makes each rival see the board exactly as it
stood the instant before this move resolved - an empty or
enemy-occupied `destination` - which is the actual question
disambiguation is asking. This only ever touches Board's public
move_piece() (the same method _resolve_arrival() itself uses), never
its private dicts.
"""

from __future__ import annotations

from typing import Optional

from kungfu_chess.model.board import Board
from kungfu_chess.model.piece import Piece
from kungfu_chess.model.position import Position
from kungfu_chess.rules.piece_rules import legal_destinations
import kungfu_chess.config as config

_KIND_LETTERS = {
    config.KING: 'K',
    config.QUEEN: 'Q',
    config.ROOK: 'R',
    config.BISHOP: 'B',
    config.KNIGHT: 'N',
    config.PAWN: '',
}


def _square(board: Board, position: Position) -> str:
    file_letter = chr(ord('a') + position.col)
    rank_number = board.height - position.row
    return f"{file_letter}{rank_number}"


def _disambiguator(board: Board, piece: Piece, source: Position, destination: Position) -> str:
    board.move_piece(destination, source)
    try:
        rivals = [
            other for other in board.all_pieces()
            if other.id != piece.id
            and other.kind == piece.kind
            and other.color == piece.color
            and destination in legal_destinations(board, other)
        ]
    finally:
        board.move_piece(source, destination)

    if not rivals:
        return ""

    same_file = any(rival.cell.col == source.col for rival in rivals)
    same_rank = any(rival.cell.row == source.row for rival in rivals)
    if not same_file:
        return chr(ord('a') + source.col)
    if not same_rank:
        return str(board.height - source.row)
    return f"{chr(ord('a') + source.col)}{board.height - source.row}"


def build_san(board: Board, piece: Piece, moved_kind: str, source: Position,
              destination: Position, is_capture: bool,
              promoted_to: Optional[str]) -> str:
    """`piece` is the moved piece as it now sits on `board` (already at
    `destination`, possibly already promoted) - `moved_kind` is passed
    separately because it must be the kind *before* any promotion
    (a pawn promoting to a queen is still written as e.g. "e8=Q", never
    "Qe8=Q")."""
    dest_square = _square(board, destination)
    letter = _KIND_LETTERS[moved_kind]

    if moved_kind == config.PAWN:
        prefix = f"{chr(ord('a') + source.col)}x" if is_capture else ""
        san = f"{prefix}{dest_square}"
    else:
        disambiguator = _disambiguator(board, piece, source, destination)
        capture_marker = "x" if is_capture else ""
        san = f"{letter}{disambiguator}{capture_marker}{dest_square}"

    if promoted_to is not None:
        san += f"={_KIND_LETTERS[promoted_to]}"

    return san
