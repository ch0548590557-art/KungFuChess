"""
GameRenderer: turns one GameSnapshot + a clock reading into one drawn Img
canvas. Board + pieces + transparency + smooth in-between-cells motion.
Never calls anything on GameEngine - only reads a GameSnapshot it's handed.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from kungfu_chess.engine.game_engine import GameSnapshot
from kungfu_chess.graphics.animation import Animation
from kungfu_chess.graphics.asset_loader import AssetLoader
from kungfu_chess.graphics.board_geometry import BoardGeometry
from kungfu_chess.graphics.img import Img
from kungfu_chess.graphics.move_log import MoveLog
from kungfu_chess.graphics.move_log_renderer import MoveLogRenderer
from kungfu_chess.graphics.score import DEFAULT_POINT_VALUES, scores_from_captures

_CAPTURED = "CAPTURED"

_COLOR_NAME = {"w": "White", "b": "Black"}

# Engine PieceState.name -> asset-pack animation-state folder name.
_ENGINE_STATE_TO_ANIMATION_STATE = {
    "IDLE": "idle",
    "MOVING": "move",
    "JUMPING": "jump",
}

CellKey = Tuple[int, int]
AnimationKey = Tuple[str, str]  # (piece_token, animation_state)

# Fixed pixel width of each side panel. Wide enough for the name +
# score line AND the two-column Time|Move table below it - "00:02.314"
# plus a SAN string up to ~6-7 chars ("Ncd6", "a8=Q") side by side -
# without needing per-string pixel-width measurement (Img exposes no
# such API). 150px (this project's original size) was sized only for
# the one-line name+score; verified by rendering a real frame to PNG
# and inspecting it (see kungfu_chess/graphics/game_renderer.py history).
_DEFAULT_PANEL_WIDTH_PX = 240

# BGRA - a plain dark strip, distinct from the board itself, that both
# panels' text sits on. Kept 4-channel (matching the sprites' own RGBA)
# so Img.draw_on never has to convert - and therefore never mutates - a
# cached sprite frame's channel count as a side effect of blitting it.
_PANEL_BG_COLOR = (40, 40, 40, 255)
_PANEL_TEXT_COLOR = (255, 255, 255, 255)


class GameRenderer:
    def __init__(self, asset_loader: AssetLoader, geometry: BoardGeometry,
                 point_values: Optional[Dict[str, int]] = None,
                 panel_width_px: int = _DEFAULT_PANEL_WIDTH_PX,
                 move_log: Optional[MoveLog] = None,
                 move_log_renderer: Optional[MoveLogRenderer] = None):
        self._assets = asset_loader
        self._geometry = geometry
        self._point_values = point_values if point_values is not None else DEFAULT_POINT_VALUES
        self._panel_width_px = panel_width_px
        # MoveLog/MoveLogRenderer default to owned instances (same DI
        # shape already used for panel_width_px above: injectable for
        # tests that need a specific fake/spy, self-constructed
        # otherwise) rather than forcing every real call site
        # (kungfu_chess/app.py) to know these two collaborators exist.
        # MoveLog itself still needs to be *one persistent instance
        # kept alive across frames* (its whole incremental-cursor point)
        # - exactly like self._animations below - so it is created once
        # here in __init__, never per-render().
        self._move_log = move_log if move_log is not None else MoveLog()
        self._move_log_renderer = move_log_renderer if move_log_renderer is not None else MoveLogRenderer()
        self._animations: Dict[CellKey, Animation] = {}
        self._animation_keys: Dict[CellKey, AnimationKey] = {}

    @property
    def left_panel_width_px(self) -> int:
        """How many pixels of the rendered canvas, on its left edge, are
        NOT board - i.e. the x-offset the board (and therefore every
        mouse click meant for it) sits at. GameWindow reads this to turn
        a raw window click back into a board-relative one before handing
        it to InputRouter, instead of GameRenderer reaching into input/
        itself or InputRouter having to know this layout decision."""
        return self._panel_width_px

    def render(self, snapshot: GameSnapshot, now_ms: int) -> Img:
        board = self._assets.board()
        canvas = Img.blank(board.width + 2 * self._panel_width_px, board.height,
                            color=_PANEL_BG_COLOR)
        # board.copy(), not board() itself, is the one being drawn onto
        # canvas (self=copy, other_img=canvas in Img.draw_on) - so any
        # one-time channel conversion draw_on performs lands on this
        # frame's throwaway copy, never permanently mutating the cached
        # asset, exactly like the pre-panel code already did for pieces.
        board.copy().draw_on(canvas, self._panel_width_px, 0)

        motions = snapshot.motions or {}
        live_keys: set[CellKey] = set()

        for kind, color, row, col, state in snapshot.pieces:
            if state == _CAPTURED:
                continue

            cell_key = (row, col)
            live_keys.add(cell_key)

            token = AssetLoader.piece_token(color, kind)
            animation_state = _ENGINE_STATE_TO_ANIMATION_STATE.get(state, "idle")
            animation = self._animation_for(cell_key, token, animation_state, now_ms)
            sprite = animation.current_frame(now_ms)

            x, y = self._pixel_position(cell_key, row, col, motions, now_ms)
            sprite.draw_on(canvas, x + self._panel_width_px, y)

        self._forget_stale_animations(live_keys)

        scores = scores_from_captures(snapshot.captures or [], self._point_values)
        self._move_log.update(snapshot.completed_moves)
        self._draw_side_panels(canvas, scores)

        if snapshot.game_over:
            self._draw_game_over_overlay(canvas, snapshot)

        return canvas

    # ---- internals ------------------------------------------------------

    def _draw_side_panels(self, canvas: Img, scores: Dict[str, int]) -> None:
        """Always-on (every frame, win or not) name + running score +
        Time|Move table for each side, drawn directly onto the panel
        strips reserved by render(). Per this session's layout spec,
        the LEFT strip is Black's panel and the RIGHT strip is White's
        (last session had them the other way around) - left_x/right_x
        below are still just "the two panels' own x positions"; only
        which _COLOR_NAME/scores/move_log key gets drawn into which one
        changed. Scoring is computed fresh from snapshot.captures every
        call rather than cached, since captures is already the full,
        current, cumulative history each time (GameEngine hands us the
        whole list, not a delta) - no extra state to keep in sync here,
        and scores_from_captures is cheap enough to call unconditionally
        on every frame. self._move_log, unlike scores, IS state kept
        across frames (see its own incremental-cursor docstring) - only
        its already-produced rows are read here.
        """
        left_x = 12
        right_x = self._panel_width_px + self._assets.board().width + 12
        table_bottom_y = canvas.height - 12

        canvas.put_text(_COLOR_NAME['b'], left_x, 40, font_size=0.8, color=_PANEL_TEXT_COLOR)
        canvas.put_text(f"Score: {scores['b']}", left_x, 70, font_size=0.7, color=_PANEL_TEXT_COLOR)
        self._move_log_renderer.draw(canvas, self._move_log, 'b', left_x, 100, table_bottom_y)

        canvas.put_text(_COLOR_NAME['w'], right_x, 40, font_size=0.8, color=_PANEL_TEXT_COLOR)
        canvas.put_text(f"Score: {scores['w']}", right_x, 70, font_size=0.7, color=_PANEL_TEXT_COLOR)
        self._move_log_renderer.draw(canvas, self._move_log, 'w', right_x, 100, table_bottom_y)

    def _draw_game_over_overlay(self, canvas: Img, snapshot: GameSnapshot) -> None:
        """The end-of-game banner - drawn on top of the board area (offset
        past the left panel so it doesn't collide with that panel's own
        text) via Img's own put_text(), same as everywhere else in this
        class. The per-side scores are already always visible in the side
        panels now, so this overlay only adds what the panels don't
        already show: who won, prominently, in the middle of the board.
        """
        winner_name = _COLOR_NAME.get(snapshot.winner, "?")
        loser_color = 'b' if snapshot.winner == 'w' else 'w'
        loser_name = _COLOR_NAME.get(loser_color, "?")

        overlay_x = self._panel_width_px + 20
        canvas.put_text(f"GAME OVER - {winner_name} wins!", overlay_x, 40, font_size=1.2)
        canvas.put_text(f"{loser_name} loses", overlay_x, 75, font_size=0.9)

    def _animation_for(self, cell_key: CellKey, token: str, animation_state: str,
                        now_ms: int) -> Animation:
        wanted_key = (token, animation_state)
        if self._animation_keys.get(cell_key) != wanted_key:
            state_assets = self._assets.state_assets(token, animation_state)
            self._animations[cell_key] = Animation(state_assets, started_at_ms=now_ms)
            self._animation_keys[cell_key] = wanted_key
        return self._animations[cell_key]

    def _pixel_position(self, cell_key: CellKey, row: int, col: int,
                         motions: dict, now_ms: int) -> Tuple[int, int]:
        motion = motions.get(cell_key)
        if motion is None:
            return self._geometry.cell_to_pixel(row, col)

        dst_row, dst_col, start_ms, arrival_ms = motion
        progress = self._progress(now_ms, start_ms, arrival_ms)
        return self._geometry.interpolated_pixel(row, col, dst_row, dst_col, progress)

    @staticmethod
    def _progress(now_ms: int, start_ms: int, arrival_ms: int) -> float:
        if arrival_ms <= start_ms:
            return 1.0
        return (now_ms - start_ms) / (arrival_ms - start_ms)

    def _forget_stale_animations(self, live_keys: set[CellKey]) -> None:
        stale = set(self._animation_keys) - live_keys
        for key in stale:
            del self._animation_keys[key]
            del self._animations[key]