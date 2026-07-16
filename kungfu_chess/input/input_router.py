from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from kungfu_chess.graphics.board_geometry import BoardGeometry
from kungfu_chess.input.controller import Controller
import kungfu_chess.config as config


@dataclass
class _PendingClick:
    x: int
    y: int
    cell: Tuple[int, int]
    time_ms: int


class InputRouter:
    def __init__(self, controller: Controller, geometry: BoardGeometry,
                 board_offset: Tuple[int, int] = (0, 0),
                 enabled: bool = True,
                 double_click_window_ms: int = config.DOUBLE_CLICK_WINDOW_MS):
        self._controller = controller
        self._geometry = geometry
        self._offset_x, self._offset_y = board_offset
        self.enabled = enabled
        self._window_ms = double_click_window_ms
        self._pending: Optional[_PendingClick] = None

    def on_mouse_down(self, x: int, y: int, now_ms: int) -> None:
        if not self.enabled:
            return

        board_x = x - self._offset_x
        board_y = y - self._offset_y
        cell = self._geometry.pixel_to_cell(board_x, board_y)

        if self._pending is not None:
            same_cell = cell == self._pending.cell
            within_window = (now_ms - self._pending.time_ms) <= self._window_ms
            if same_cell and within_window:
                self._controller.jump(board_x, board_y)
                self._pending = None
                return

        self._pending = _PendingClick(board_x, board_y, cell, now_ms)

    def tick(self, now_ms: int) -> None:
        if not self.enabled or self._pending is None:
            return

        if (now_ms - self._pending.time_ms) > self._window_ms:
            self._controller.click(self._pending.x, self._pending.y)
            self._pending = None
