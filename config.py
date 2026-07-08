"""Central configuration for values that used to be 'magic numbers' or
magic strings scattered through the business logic (e.g. the 1000ms move
duration, the 100px grid size, the letter 'Q' pawns promote to).

Nothing here changes behavior - every value below is exactly what the
original script used. The only difference is that they now live in ONE
place, so a future change (e.g. "promote to a Queen OR let the user pick")
means editing this file instead of hunting through engine logic.
"""

PIXELS_PER_SQUARE = 100      # click/jump coordinates arrive in pixels
MOVE_DURATION_MS = 1000      # time a normal move takes to arrive
JUMP_DURATION_MS = 1000      # time a piece stays "airborne" after a jump

KING_TYPE = 'K'
PAWN_TYPE = 'P'
PROMOTION_PIECE_TYPE = 'Q'   # what a pawn promotes to

VALID_PIECE_TYPES = {'K', 'Q', 'R', 'B', 'N', 'P'}
VALID_COLORS = {'w', 'b'}
