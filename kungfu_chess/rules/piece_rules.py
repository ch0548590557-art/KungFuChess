"""
Movement geometry, one small function per piece type, chosen through a
dispatch dict instead of a growing if/elif chain.

WHY A DICT DISPATCH (Strategy pattern) INSTEAD OF ONE BIG FUNCTION:
The old project (files.zip, piece_rules.py) already made this exact
choice and the comment there explains it well: an if/elif chain grows
every time a new piece type is added and mixes every piece's logic into
one function's local variables. A dict mapping kind -> function means
`legal_destinations()` doesn't need to know how many piece types exist;
adding a 7th piece type later is "write one function, add one dict
entry", not "find the right spot in a 40-line elif chain without breaking
an existing branch". This is the textbook Strategy pattern: each piece
kind is an interchangeable strategy for the same question
("where can I go?"), selected at runtime by a key.

WHY EACH RULE RETURNS A set[Position] OF DESTINATIONS INSTEAD OF A
bool "is this specific move legal":
RuleEngine (Section 8) ultimately just needs "is destination in
legal_destinations(board, piece)". But returning the *whole* set (not a
single yes/no) means the exact same function can also answer "highlight
all squares this piece could move to" for the renderer later, without a
second code path. One function, two future callers, same source of truth
- there is no boolean-only twin to keep in sync with the set-returning
one.

WHY THESE FUNCTIONS ARE STATELESS (Section 7):
No rule function stores selected pieces, active motions, or game-over
state - they only read `board` and `piece` and compute an answer. That
statelessness is what makes them trivially unit-testable in isolation
(Iteration 3): construct a Board, put a piece on it, call the function,
assert the returned set. No GameEngine, no RuleEngine, no fixtures beyond
a Board.

WHY SLIDING PIECES SHARE A _slide() HELPER:
Rook, Bishop and Queen differ only in *which directions* they slide, not
in *how* sliding works (walk a direction, stop before/at the first
occupied square, include an enemy blocker as a legal destination, exclude
a friendly blocker). Extracting that shared walk-until-blocked loop keeps
each of the three rule functions to a one-line list of directions, and a
bug fix in "how sliding stops" only has to be made once.
"""

from typing import Set

from kungfu_chess.model.position import Position
from kungfu_chess.model.piece import Piece
from kungfu_chess.model.board import Board
import kungfu_chess.config as config

_ROOK_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
_BISHOP_DIRS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
_KING_DIRS = _ROOK_DIRS + _BISHOP_DIRS
_KNIGHT_OFFSETS = [
    (-2, -1), (-2, 1), (2, -1), (2, 1),
    (-1, -2), (-1, 2), (1, -2), (1, 2),
]


def _slide(board: Board, piece: Piece, directions) -> Set[Position]:
    destinations = set()
    for dr, dc in directions:
        r, c = piece.cell.row + dr, piece.cell.col + dc
        while True:
            pos = Position(r, c)
            if not board.in_bounds(pos):
                break
            occupant = board.piece_at(pos)
            if occupant is None:
                destinations.add(pos)
            else:
                if occupant.color != piece.color:
                    destinations.add(pos)  # enemy blocker: legal, but stop
                break  # friendly or enemy blocker both stop the slide
            r, c = r + dr, c + dc
    return destinations


def _rook_destinations(board, piece) -> Set[Position]:
    return _slide(board, piece, _ROOK_DIRS)


def _bishop_destinations(board, piece) -> Set[Position]:
    return _slide(board, piece, _BISHOP_DIRS)


def _queen_destinations(board, piece) -> Set[Position]:
    return _slide(board, piece, _KING_DIRS)


def _knight_destinations(board, piece) -> Set[Position]:
    destinations = set()
    for dr, dc in _KNIGHT_OFFSETS:
        pos = Position(piece.cell.row + dr, piece.cell.col + dc)
        if board.in_bounds(pos):
            occupant = board.piece_at(pos)
            if occupant is None or occupant.color != piece.color:
                destinations.add(pos)
    return destinations


def _king_destinations(board, piece) -> Set[Position]:
    destinations = set()
    for dr, dc in _KING_DIRS:
        pos = Position(piece.cell.row + dr, piece.cell.col + dc)
        if board.in_bounds(pos):
            occupant = board.piece_at(pos)
            if occupant is None or occupant.color != piece.color:
                destinations.add(pos)
    return destinations


def _pawn_destinations(board, piece) -> Set[Position]:
    """Simplified pawn (Section 7): one step forward only, no two-step
    opening, no en passant, no promotion. Forward direction is derived
    from color so this one function serves both colors."""
    destinations = set()
    forward = -1 if piece.color == 'w' else 1
    r, c = piece.cell.row + forward, piece.cell.col

    forward_pos = Position(r, c)
    if board.in_bounds(forward_pos) and board.is_empty(forward_pos):
        destinations.add(forward_pos)

    for dc in (-1, 1):
        cap_pos = Position(r, c + dc)
        if board.in_bounds(cap_pos):
            occupant = board.piece_at(cap_pos)
            if occupant is not None and occupant.color != piece.color:
                destinations.add(cap_pos)

    return destinations


PIECE_RULES = {
    config.ROOK: _rook_destinations,
    config.BISHOP: _bishop_destinations,
    config.QUEEN: _queen_destinations,
    config.KNIGHT: _knight_destinations,
    config.KING: _king_destinations,
    config.PAWN: _pawn_destinations,
}


def legal_destinations(board: Board, piece: Piece) -> Set[Position]:
    rule = PIECE_RULES[piece.kind]
    return rule(board, piece)
