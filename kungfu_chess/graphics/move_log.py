"""
MoveLog: pure model that turns GameEngine's cumulative
GameSnapshot.completed_moves list - (color, san, timestamp_ms) tuples,
append-only, in completion order (kungfu_chess/engine/game_engine.py) -
into two persistent per-color lists of already-formatted display rows:
(time_str, san). No Img/cv2 here; MoveLogRenderer owns drawing, this
class only owns the data transform, the same split score.py already
uses between "compute the numbers" and GameRenderer "draw the numbers".

WHY AN INCREMENTAL CURSOR INSTEAD OF RE-DERIVING THE TWO PER-COLOR LISTS
FROM SCRATCH ON EVERY update() CALL:
completed_moves is handed to this class as a fresh full-history list
copy every single frame (same contract GameSnapshot.captures already
has), and is explicitly expected to grow into the hundreds of entries
over one game. GameRenderer.render() runs once per rendered frame, so
re-scanning and re-splitting the *whole* list on every call would mean
redoing an ever-growing amount of work for what is, almost every frame,
zero or one new entries. Instead this class remembers how many of the
shared list's leading entries it has already turned into rows
(self._consumed) and, on each update(), only iterates the new tail
slice completed_moves[self._consumed:], appending each row's formatted
(time_str, san) onto whichever color's persistent row list it belongs
to. Rows already appended are never touched again - no reordering, no
overwrite - mirroring the append-only guarantee of the source list.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

MoveRow = Tuple[str, str]  # (formatted time "MM:SS.mmm", san)
CompletedMove = Tuple[str, str, int]  # (color, san, timestamp_ms)


def format_move_time(timestamp_ms: int) -> str:
    """MM:SS.mmm, e.g. "00:02.314" - minutes from timestamp_ms // 60000,
    no hour rollover (per spec: engine games never run that long). A
    free function rather than a method since it has no state of its own
    and both MoveLog and, potentially, a future caller can reuse it
    without needing a MoveLog instance to do so.
    """
    total_seconds, ms = divmod(timestamp_ms, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}.{ms:03d}"


class MoveLog:
    """Keep-alive-across-frames model: construct one instance, call
    update(snapshot.completed_moves) once per frame, then read
    rows_for('w') / rows_for('b') for display. Deliberately stateful
    (unlike score.py's scores_from_captures, which is cheap enough to
    recompute from scratch every frame) precisely because re-deriving
    it from scratch is the thing this class exists to avoid.
    """

    def __init__(self):
        self._consumed = 0
        self._rows: Dict[str, List[MoveRow]] = {'w': [], 'b': []}

    def update(self, completed_moves: Optional[Sequence[CompletedMove]]) -> None:
        """Consume only the entries beyond what was already processed.
        `completed_moves` defensively defaults to [] when None/missing,
        matching the existing `snapshot.captures or []` pattern already
        used elsewhere in graphics/. If a shorter-than-before list is
        ever handed in (should never happen given the source's
        append-only contract, but this class does not trust that
        blindly) it is treated as "nothing new yet" rather than as a
        reason to rewind the cursor and reprocess already-consumed
        entries into duplicate rows.
        """
        moves = completed_moves or []
        if len(moves) <= self._consumed:
            return

        for color, san, timestamp_ms in moves[self._consumed:]:
            self._rows.setdefault(color, []).append((format_move_time(timestamp_ms), san))
        self._consumed = len(moves)

    def rows_for(self, color: str) -> List[MoveRow]:
        """A fresh copy of that color's rows so far, oldest first -
        never the live internal list - so a caller (e.g.
        MoveLogRenderer slicing off the newest N for auto-scroll) can
        never accidentally mutate this model's own state."""
        return list(self._rows.get(color, []))
