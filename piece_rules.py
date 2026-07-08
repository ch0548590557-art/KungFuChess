"""Movement legality rules for each piece type.

Instead of one long if/elif chain (which grows every time a new piece type
is added, and mixes all pieces' logic into a single function), each piece
type gets its own small function, and PIECE_MOVE_RULES maps a piece letter
to its function. is_legal_move() just looks the function up and calls it -
it doesn't need to know how many piece types exist or what their rules are.
"""

import config


def is_path_clear(board, r1, c1, r2, c2):
    """True if every square strictly between (r1, c1) and (r2, c2) is empty.
    Used by any piece that "slides" (rook, bishop, queen, and a pawn's
    two-square opening move)."""
    dr = r2 - r1
    dc = c2 - c1

    step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
    step_c = 0 if dc == 0 else (1 if dc > 0 else -1)

    curr_r = r1 + step_r
    curr_c = c1 + step_c

    while curr_r != r2 or curr_c != c2:
        if not board.is_empty(curr_r, curr_c):
            return False
        curr_r += step_r
        curr_c += step_c

    return True


def _king_rule(board, r1, c1, r2, c2, dr, dc):
    return dr <= 1 and dc <= 1


def _rook_rule(board, r1, c1, r2, c2, dr, dc):
    if dr == 0 or dc == 0:
        return is_path_clear(board, r1, c1, r2, c2)
    return False


def _bishop_rule(board, r1, c1, r2, c2, dr, dc):
    if dr == dc:
        return is_path_clear(board, r1, c1, r2, c2)
    return False


def _queen_rule(board, r1, c1, r2, c2, dr, dc):
    if dr == 0 or dc == 0 or dr == dc:
        return is_path_clear(board, r1, c1, r2, c2)
    return False


def _knight_rule(board, r1, c1, r2, c2, dr, dc):
    return (dr == 1 and dc == 2) or (dr == 2 and dc == 1)


def _pawn_rule(board, r1, c1, r2, c2, dr, dc):
    color = board.color_at(r1, c1)
    allowed_dr = -1 if color == 'w' else 1
    actual_dr = r2 - r1

    is_destination_empty = board.is_empty(r2, c2)

    # one square forward
    if dc == 0 and actual_dr == allowed_dr:
        return is_destination_empty

    # two squares forward, only from the starting row
    is_start_row = (r1 == board.height - 1 if color == 'w' else r1 == 0)
    if dc == 0 and actual_dr == allowed_dr * 2 and is_start_row:
        return is_destination_empty and is_path_clear(board, r1, c1, r2, c2)

    # diagonal capture
    if dc == 1 and actual_dr == allowed_dr:
        return not is_destination_empty

    return False


# The dispatch table: this is the single place that lists which piece
# letters exist and which function governs each one.
PIECE_MOVE_RULES = {
    config.KING_TYPE: _king_rule,
    'Q': _queen_rule,
    'R': _rook_rule,
    'B': _bishop_rule,
    'N': _knight_rule,
    config.PAWN_TYPE: _pawn_rule,
}


def is_legal_move(board, piece_type, r1, c1, r2, c2):
    dr = abs(r2 - r1)
    dc = abs(c2 - c1)

    if dr == 0 and dc == 0:
        return False

    # can't capture your own color
    if not board.is_empty(r2, c2) and board.color_at(r1, c1) == board.color_at(r2, c2):
        return False

    rule = PIECE_MOVE_RULES.get(piece_type)
    if rule is None:
        return True  # unknown piece type: same permissive fallback as before

    return rule(board, r1, c1, r2, c2, dr, dc)
