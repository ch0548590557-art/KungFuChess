"""
Position: a value object representing a board cell (row, col).

WHY A DATACLASS:
Position has no behavior beyond "carry two integers, compare equal when
both match, and print nicely for failing test output". @dataclass writes
__init__, __eq__ and __repr__ for us from the field list, so there is no
hand-written boilerplate that could drift out of sync with the fields.
`frozen=True` makes it immutable and hashable, which matters because
Positions are used as dict keys / set members in Board and in
legal_destinations() results (Iteration 3) - a mutable, unhashable
Position would silently break "was this square already visited?" checks.

WHY NOT A PLAIN TUPLE (row, col):
A tuple would technically work, but `pos.row` / `pos.col` is far more
readable at every call site than `pos[0]` / `pos[1]`, and a dataclass lets
us add validation or methods later (e.g. `.offset(dr, dc)`) without
touching every caller.

WHAT IT DELIBERATELY DOES NOT KNOW:
Board size, whether the cell is on the board, what piece (if any) sits on
it, or pixels. Bounds checking belongs to Board (Section 6 of the design
guide) - putting it here would mean Position could not be constructed
without knowing about a specific board, coupling two things that should
stay independent.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    row: int
    col: int

    def __repr__(self):
        return f"Position(row={self.row}, col={self.col})"
