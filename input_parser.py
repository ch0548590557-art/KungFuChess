"""Turns raw stdin lines into (board_rows, commands), or raises InputError
for malformed input. This is purely about the TEXT FORMAT of the input -
it doesn't know anything about game rules, timing, or the engine.
"""

import config


class InputError(Exception):
    """Carries the exact error message the original script used to print."""
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def parse_lines(raw_lines):
    lines = [l.strip() for l in raw_lines if l.strip()]

    if not lines or "Board:" not in lines[0]:
        return None, None

    b_idx = lines.index("Board:")
    c_idx = lines.index("Commands:")

    board_rows = [row.split() for row in lines[b_idx + 1:c_idx]]
    commands = lines[c_idx + 1:]

    if not board_rows:
        return None, None

    _validate_board(board_rows)

    return board_rows, commands


def _validate_board(board_rows):
    width = len(board_rows[0])

    if any(len(row) != width for row in board_rows):
        raise InputError("ERROR ROW_WIDTH_MISMATCH")

    for row in board_rows:
        for token in row:
            if token != '.' and not _is_valid_token(token):
                raise InputError("ERROR UNKNOWN_TOKEN")


def _is_valid_token(token):
    return (
        len(token) == 2
        and token[0] in config.VALID_COLORS
        and token[1] in config.VALID_PIECE_TYPES
    )
