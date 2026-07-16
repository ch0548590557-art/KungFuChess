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

# --- Extra route: "Jump" (airborne / untouchable-window ability) ----------
# How long (ms) a piece stays airborne after jumping before it lands back
# on its own cell. A single constant here (rather than hard-coding 1000 in
# RealTimeArbiter) keeps the "how long is the jump window" decision in the
# same one place as every other timing knob (CELL_SIZE_PX,
# PIECE_SPEED_PX_PER_SEC above), so tuning it later never means hunting
# through realtime/real_time_arbiter.py.
JUMP_DURATION_MS = 1000

# --- Promotion policy (Section 10 arrival-time effect) ---------------------
# Mirrors the same "one config switch, zero code-path branching" approach as
# MAX_CONCURRENT_MOTIONS above: PROMOTION_ENABLED turns the whole feature
# off without touching GameEngine/rules code, and PROMOTION_TARGETS is a
# dict dispatch (same Strategy-pattern shape as PIECE_RULES in
# rules/piece_rules.py) mapping "a piece of this kind, upon reaching the far
# rank, becomes a piece of that kind". A kind with no entry here simply
# never promotes - so disabling promotion for one piece type, or adding a
# second promotable piece type, or changing what a pawn promotes into, are
# all one-line edits here and nowhere else.
PROMOTION_ENABLED = True
PROMOTION_TARGETS = {
    PAWN: QUEEN,
}

# --- Step 6: mouse input double-click detection ----------------------------
# How long (ms) after a first click InputRouter still treats a second click
# on the same cell as a double-click (-> jump) rather than two separate,
# unrelated clicks. Same "one named knob, not a literal buried in the
# class" approach as JUMP_DURATION_MS above.
DOUBLE_CLICK_WINDOW_MS = 300
