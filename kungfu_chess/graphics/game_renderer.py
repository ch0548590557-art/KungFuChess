"""
GameRenderer: turns one GameSnapshot + a clock reading into one drawn Img
canvas. Board + pieces + transparency + smooth in-between-cells motion.
Never calls anything on GameEngine - only reads a GameSnapshot it's handed.
"""

from __future__ import annotations

from typing import Dict, Tuple

from kungfu_chess.engine.game_engine import GameSnapshot
from kungfu_chess.graphics.animation import Animation
from kungfu_chess.graphics.asset_loader import AssetLoader
from kungfu_chess.graphics.board_geometry import BoardGeometry
from kungfu_chess.graphics.img import Img

_CAPTURED = "CAPTURED"

# Engine PieceState.name -> asset-pack animation-state folder name.
_ENGINE_STATE_TO_ANIMATION_STATE = {
    "IDLE": "idle",
    "MOVING": "move",
    "JUMPING": "jump",
}

CellKey = Tuple[int, int]
AnimationKey = Tuple[str, str]  # (piece_token, animation_state)


class GameRenderer:
    def __init__(self, asset_loader: AssetLoader, geometry: BoardGeometry):
        self._assets = asset_loader
        self._geometry = geometry
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
        return canvas

    # ---- internals ------------------------------------------------------

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