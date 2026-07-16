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


class GameRenderer:
    def __init__(self, asset_loader: AssetLoader, geometry: BoardGeometry,
                 point_values: Optional[Dict[str, int]] = None):
        self._assets = asset_loader
        self._geometry = geometry
        self._point_values = point_values if point_values is not None else DEFAULT_POINT_VALUES
        self._animations: Dict[CellKey, Animation] = {}
        self._animation_keys: Dict[CellKey, AnimationKey] = {}

    def render(self, snapshot: GameSnapshot, now_ms: int) -> Img:
        canvas = self._assets.board().copy()
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
            sprite.draw_on(canvas, x, y)

        self._forget_stale_animations(live_keys)

        if snapshot.game_over:
            self._draw_game_over_overlay(canvas, snapshot)

        return canvas

    # ---- internals ------------------------------------------------------

    def _draw_game_over_overlay(self, canvas: Img, snapshot: GameSnapshot) -> None:
        """Draws the end-of-game text directly onto the canvas via Img's
        own put_text() - GameRenderer never touches cv2 itself, only
        Img's public API, same as everywhere else in this class. Scoring
        is computed fresh from snapshot.captures every call rather than
        cached, since captures is already the full, current, cumulative
        history each time (GameEngine hands us the whole list, not a
        delta) - no extra state to keep in sync here.
        """
        scores = scores_from_captures(snapshot.captures or [], self._point_values)
        winner_name = _COLOR_NAME.get(snapshot.winner, "?")
        loser_color = 'b' if snapshot.winner == 'w' else 'w'
        loser_name = _COLOR_NAME.get(loser_color, "?")

        canvas.put_text(f"GAME OVER - {winner_name} wins!", 20, 40, font_size=1.2)
        canvas.put_text(f"{loser_name} loses", 20, 75, font_size=0.9)
        canvas.put_text(f"White: {scores['w']}   Black: {scores['b']}", 20, 105, font_size=0.9)

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