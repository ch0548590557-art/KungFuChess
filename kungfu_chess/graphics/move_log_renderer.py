"""
MoveLogRenderer: draws one color's "Time | Move" table - a header row
plus as many of that color's newest rows as fit - into a rectangular
region of an already-existing Img canvas. Purely a rendering concern:
it reads a MoveLog's already-formatted rows and calls Img.put_text /
Img.fill_rect, and never mutates the MoveLog it is handed (MoveLog.
rows_for already hands back a fresh copy, so there is nothing here for
this class to accidentally corrupt even if it wanted to).

WHY THIS IS A SEPARATE CLASS FROM MoveLog RATHER THAN A draw() METHOD
ON MoveLog ITSELF:
MoveLog owns data (turning engine facts into rows, incrementally,
across frames); this class owns pixels (turning already-produced rows
into an Img canvas, fresh every frame, no state of its own). Mixing
them would give one class two reasons to change - a new column layout
vs. a new notation quirk - exactly the split game_renderer.py/score.py
already draw between "compute" and "draw" for the score panel.

WHY "SHOW ONLY THE NEWEST ROWS THAT FIT" IS COMPUTED HERE, NOT IN
MoveLog:
How many rows fit is a function of pixel geometry (row height, font
size, panel height) - a rendering fact, not a chess-log fact. MoveLog
keeps the *entire* history (a plain, unbounded per-color list) so nothing
is ever lost if the panel is later made taller or the game is replayed
at a different resolution; this class alone decides, per draw() call,
how much of that history is visible right now.
"""

from __future__ import annotations

from typing import Tuple

from kungfu_chess.graphics.img import Img
from kungfu_chess.graphics.move_log import MoveLog

_HEADER_TEXT_COLOR = (255, 255, 255, 255)
_ROW_TEXT_COLOR = (220, 220, 220, 255)
_DIVIDER_COLOR = (120, 120, 120, 255)


class MoveLogRenderer:
    def __init__(self, font_size: float = 0.42, row_height_px: int = 20,
                 time_column_width_px: int = 95, header_color: Tuple[int, int, int, int] = _HEADER_TEXT_COLOR,
                 row_color: Tuple[int, int, int, int] = _ROW_TEXT_COLOR,
                 divider_color: Tuple[int, int, int, int] = _DIVIDER_COLOR):
        self._font_size = font_size
        self._row_height_px = row_height_px
        self._time_column_width_px = time_column_width_px
        self._header_color = header_color
        self._row_color = row_color
        self._divider_color = divider_color

    def draw(self, canvas: Img, move_log: MoveLog, color: str,
              panel_x: int, top_y: int, bottom_y: int) -> None:
        """Draw `color`'s table into the vertical band [top_y, bottom_y)
        of `canvas`, with its left text edge at panel_x. `bottom_y` is
        normally the panel's own bottom edge (e.g. canvas.height minus a
        margin), so the visible-row count adapts to whatever room the
        caller has actually left for the table below the name/score
        text already drawn above it.
        """
        canvas.put_text("Time", panel_x, top_y, font_size=self._font_size, color=self._header_color)
        canvas.put_text("Move", panel_x + self._time_column_width_px, top_y,
                         font_size=self._font_size, color=self._header_color)

        divider_y = top_y + 6
        divider_width = self._time_column_width_px + 60
        canvas.fill_rect(panel_x, divider_y, divider_width, 2, color=self._divider_color)

        rows_top_y = divider_y + self._row_height_px
        available_height = max(0, bottom_y - rows_top_y)
        visible_count = available_height // self._row_height_px
        if visible_count <= 0:
            return

        rows = move_log.rows_for(color)
        visible_rows = rows[-visible_count:]

        for i, (time_str, san) in enumerate(visible_rows):
            row_y = rows_top_y + i * self._row_height_px
            canvas.put_text(time_str, panel_x, row_y, font_size=self._font_size, color=self._row_color)
            canvas.put_text(san, panel_x + self._time_column_width_px, row_y,
                             font_size=self._font_size, color=self._row_color)
