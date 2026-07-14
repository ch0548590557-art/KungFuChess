"""
Board: the single source of truth for "what logically sits where".

WHY A DICT[Position, Piece] INSTEAD OF A 2D LIST OF STRINGS:
The previous version of this project (files.zip) stored a raw grid of
2-character strings ('wK', '.', ...). That works, but it means "the
board" and "the pieces" are the same object, and a Piece has no stable
identity - promoting/capturing/moving all become string surgery on a
grid cell. Once RealTimeArbiter needs to track a *specific* piece across
time (Section 10) and, per Iteration 10, track *several* pieces moving
at once, "identity" stops being optional. A dict keyed by Position with
Piece objects as values keeps O(1) lookup by cell (same cost as the old
grid) while giving every piece a stable `.id` that survives being moved.

WHY BOTH _by_cell AND _by_id:
Two different questions get asked of Board by two different layers:
  - "what's on square X?" -> RuleEngine, PieceRules, BoardPrinter (by cell)
  - "where is piece #7 right now?" -> RealTimeArbiter, when an arrival
    event needs to update the piece that a Motion was tracking (by id)
Keeping one dict per question means each lookup stays O(1) instead of
scanning all pieces. This is a small, deliberate space-for-time trade,
justified because both queries happen on every tick / every click.

WHAT BOARD DELIBERATELY DOES NOT DO:
- It does not decide whether a move is *legal* (that's PieceRules /
  RuleEngine). move_piece() assumes the caller already validated.
- It does not know about pixels, clicks, or Motion/time.
- It does not call RuleEngine, ever - keeping the dependency direction
  one-way (Board depends on nothing above it, per Section 5).
"""

from typing import Dict, Optional

from kungfu_chess.model.position import Position
from kungfu_chess.model.piece import Piece, PieceState


class DuplicateOccupancyError(Exception):
    pass


class Board:
    def __init__(self, width: int, height: int):
        self._width = width
        self._height = height
        self._by_cell: Dict[Position, Piece] = {}
        self._by_id: Dict[int, Piece] = {}

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def in_bounds(self, pos: Position) -> bool:
        return 0 <= pos.row < self._height and 0 <= pos.col < self._width

    def piece_at(self, pos: Position) -> Optional[Piece]:
        return self._by_cell.get(pos)

    def piece_by_id(self, piece_id: int) -> Optional[Piece]:
        return self._by_id.get(piece_id)

    def is_empty(self, pos: Position) -> bool:
        return pos not in self._by_cell

    def add_piece(self, piece: Piece) -> None:
        if piece.cell in self._by_cell:
            raise DuplicateOccupancyError(
                f"cell {piece.cell} already occupied"
            )
        if piece.id in self._by_id:
            raise DuplicateOccupancyError(
                f"piece id {piece.id} already exists on this board"
            )
        self._by_cell[piece.cell] = piece
        self._by_id[piece.id] = piece

    def remove_piece(self, pos: Position) -> Optional[Piece]:
        piece = self._by_cell.pop(pos, None)
        if piece is not None:
            self._by_id.pop(piece.id, None)
            piece.state = PieceState.CAPTURED
        return piece

    def detach_piece(self, pos: Position) -> Optional[Piece]:
        piece = self._by_cell.pop(pos, None)
        return piece

    def place_piece(self, piece: Piece) -> None:
        if piece.cell in self._by_cell:
            raise DuplicateOccupancyError(
                f"cell {piece.cell} already occupied"
            )
        self._by_cell[piece.cell] = piece
        if piece.id not in self._by_id:
            self._by_id[piece.id] = piece

    def move_piece(self, source: Position, destination: Position) -> None:
        """Relocates the piece at `source` to `destination`. Assumes the
        caller (GameEngine / RealTimeArbiter) already validated legality
        and already resolved any capture at the destination - Board only
        moves state around, it never decides correctness."""
        piece = self._by_cell.pop(source)
        piece.cell = destination
        self._by_cell[destination] = piece

    def all_pieces(self):
        return list(self._by_id.values())

    def row_tokens(self):
        """2-char token grid ('wK', '.', ...) for BoardPrinter. Kept here
        (not in BoardPrinter) because it is a straightforward projection
        of Board's own occupancy data, not text-formatting logic."""
        grid = [['.' for _ in range(self._width)] for _ in range(self._height)]
        for pos, piece in self._by_cell.items():
            grid[pos.row][pos.col] = f"{piece.color}{piece.kind}"
        return grid
