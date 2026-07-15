"""
BoardGeometry: pure pixel-coordinate math. No Img, no cv2, no state -
just "given a cell, or two cells and a progress fraction, where in
pixels does that land".
"""

from __future__ import annotations


class BoardGeometry:
    def __init__(self, cell_size_px: int):
        self.cell_size_px = cell_size_px

    def cell_to_pixel(self, row: int, col: int) -> tuple[int, int]:
        """Top-left pixel of (row, col), in (x, y) order to match
        Img.draw_on(canvas, x, y): x is horizontal (col), y is vertical (row)."""
        return col * self.cell_size_px, row * self.cell_size_px

    def pixel_to_cell(self, x: int, y: int) -> tuple[int, int]:
        """Inverse of cell_to_pixel - needed by Step 6's mouse input."""
        return y // self.cell_size_px, x // self.cell_size_px

    def interpolated_pixel(self, src_row: int, src_col: int,
                            dst_row: int, dst_col: int,
                            progress: float) -> tuple[int, int]:
        """display_x = start_x + progress * (target_x - start_x)."""
        progress = max(0.0, min(1.0, progress))
        start_x, start_y = self.cell_to_pixel(src_row, src_col)
        target_x, target_y = self.cell_to_pixel(dst_row, dst_col)
        x = start_x + progress * (target_x - start_x)
        y = start_y + progress * (target_y - start_y)
        return int(round(x)), int(round(y))