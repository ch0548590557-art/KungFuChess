"""
Single source of truth for values that would otherwise be "magic numbers"
scattered across layers (pixel size, move speed, legal piece letters).

Every other module imports from here instead of hard-coding a literal, so
a future change (e.g. a bigger board on screen) means editing ONE file.
"""

CELL_SIZE_PX = 100          # width/height of one board square, in pixels
PIECE_SPEED_PX_PER_SEC = 100  # -> exactly 1000ms to cross one square

KING = 'K'
QUEEN = 'Q'
ROOK = 'R'
BISHOP = 'B'
KNIGHT = 'N'
PAWN = 'P'

VALID_KINDS = {KING, QUEEN, ROOK, BISHOP, KNIGHT, PAWN}
VALID_COLORS = {'w', 'b'}

# --- Extra-route knob (Iteration 10: "Simultaneous movement") -------------
# None  -> unlimited pieces may move at the same time (extra route: ON)
# 1     -> common-route behaviour restored: only one active motion overall
# N>1   -> capped at N concurrent motions (useful for tuning/testing)
#
# This single constant is the whole "flexibility" switch: nothing else in
# the codebase needs to change to move between common-route and
# extra-route concurrency behaviour. See RealTimeArbiter.
MAX_CONCURRENT_MOTIONS = None
