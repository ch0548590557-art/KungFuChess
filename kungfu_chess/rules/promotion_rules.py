"""
promotion_rules: WHAT a piece promotes into (policy), kept separate from
WHEN promotion happens (timing).

WHY THIS FILE EXISTS AT ALL, GIVEN GameEngine ALREADY CALLED THIS INLINE:
The original implementation put both the *timing* decision ("promotion is
an arrival-time effect, so check it right after every ArrivalEvent") and
the *policy* decision ("a PAWN reaching the far rank becomes a QUEEN,
always, unconditionally") in GameEngine._maybe_promote. The timing part is
correctly GameEngine's job (Section 10: it's the one layer allowed to
react to "this arrived"). The policy part is not - it's exactly the same
kind of question piece_rules.PIECE_RULES already answers for movement
("what can a piece of this kind do"), just for a different verb
("what does a piece of this kind turn into"). Leaving policy inline in
GameEngine meant changing "should pawns even promote" or "promote to what"
required editing orchestration code instead of a rules file or a config
value - the one inconsistency in an otherwise config/dispatch-driven
codebase (compare config.MAX_CONCURRENT_MOTIONS and piece_rules.
PIECE_RULES, which both make exactly this kind of policy a one-line
change).

WHY A FUNCTION HERE INSTEAD OF JUST READING config.PROMOTION_TARGETS
DIRECTLY FROM GameEngine:
Two independent conditions decide whether a promotion happens: the global
config.PROMOTION_ENABLED switch, and "is this piece's kind even in the
targets dict, and is it actually standing on the far rank right now".
Bundling both checks into one function keeps GameEngine's call site to a
single line ("what, if anything, does this piece become") instead of
GameEngine re-deriving "which rank is 'the far rank' for this color" or
re-checking the enabled flag itself - exactly the same reason RuleEngine
calls piece_rules.legal_destinations() instead of re-implementing rook
geometry inline.

WHY board.height IS STILL COMPUTED HERE AND NOT PASSED IN AS A PARAMETER:
Same reasoning as _pawn_home_row() in piece_rules.py: promotion rank is
symmetric and derived from board shape (row 0 for white, board.height - 1
for black), so it has to see the board, not just the piece, to answer the
question for any board size a fixture throws at it.
"""

from typing import Optional

from kungfu_chess.model.board import Board
from kungfu_chess.model.piece import Piece
import kungfu_chess.config as config


def promotion_target(board: Board, piece: Piece) -> Optional[str]:
    """Returns the config.VALID_KINDS letter this piece should become, or
    None if it should not promote right now (feature disabled, this piece's
    kind is not promotable at all, or it simply isn't on the far rank)."""
    if not config.PROMOTION_ENABLED:
        return None

    target_kind = config.PROMOTION_TARGETS.get(piece.kind)
    if target_kind is None:
        return None

    far_rank = 0 if piece.color == 'w' else board.height - 1
    if piece.cell.row != far_rank:
        return None

    return target_kind
