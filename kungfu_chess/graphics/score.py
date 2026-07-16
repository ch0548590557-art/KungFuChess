"""
score.py: pure conversion from GameEngine's raw capture facts
(GameSnapshot.captures - a list of (kind, color) tuples: which piece
kinds were captured, and which color they belonged to) into points
earned by each side. Point values are a graphics/UI-owned policy -
GameEngine only ever reports *what* was captured, never what it is
"worth", so a rule change here (e.g. a house-rule point table) never
touches engine code.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import kungfu_chess.config as config

DEFAULT_POINT_VALUES: Dict[str, int] = {
    config.KNIGHT: 3,
    config.BISHOP: 3,
    config.ROOK: 5,
    config.QUEEN: 9,
    config.PAWN: 1,
    config.KING: 0,
}


def scores_from_captures(captures: List[Tuple[str, str]],
                          point_values: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    """`captures` is GameSnapshot.captures: (kind, color) of every piece
    captured so far, where `color` is the captured piece's OWN color
    (the losing side of that one capture). Points are credited to the
    *other* color - since Controller/RuleEngine never allow a piece to
    capture one of its own color, the opposite color is always exactly
    who did the capturing, with no extra "who captured whom" bookkeeping
    needed.
    """
    values = point_values if point_values is not None else DEFAULT_POINT_VALUES
    scores = {'w': 0, 'b': 0}
    for kind, captured_color in captures:
        capturer_color = 'b' if captured_color == 'w' else 'w'
        scores[capturer_color] += values.get(kind, 0)
    return scores
