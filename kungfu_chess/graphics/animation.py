"""
Animation: given a loaded StateAssets (from AssetLoader) and the moment
it started playing, answers "which frame right now?" for any later
clock reading.
"""

from __future__ import annotations

from kungfu_chess.graphics.asset_loader import StateAssets
from kungfu_chess.graphics.img import Img


class Animation:
    def __init__(self, state_assets: StateAssets, started_at_ms: int):
        if not state_assets.frames:
            raise ValueError("StateAssets has no frames to animate.")
        self._assets = state_assets
        self._started_at_ms = started_at_ms

    @property
    def state_assets(self) -> StateAssets:
        return self._assets

    @property
    def started_at_ms(self) -> int:
        return self._started_at_ms

    def frame_index(self, now_ms: int) -> int:
        """0-based index into state_assets.frames for this moment."""
        elapsed_ms = max(0, now_ms - self._started_at_ms)
        total_frames = len(self._assets.frames)
        fps = self._assets.frames_per_sec

        if fps <= 0 or total_frames == 1:
            return 0  # defensive: nothing to animate, hold frame 0

        frame_duration_ms = 1000.0 / fps
        raw_index = int(elapsed_ms / frame_duration_ms)

        if self._assets.is_loop:
            return raw_index % total_frames
        return min(raw_index, total_frames - 1)

    def current_frame(self, now_ms: int) -> Img:
        return self._assets.frames[self.frame_index(now_ms)]

    def is_finished(self, now_ms: int) -> bool:
        if self._assets.is_loop:
            return False

        total_frames = len(self._assets.frames)
        fps = self._assets.frames_per_sec
        if fps <= 0 or total_frames == 1:
            return True

        elapsed_ms = max(0, now_ms - self._started_at_ms)
        full_duration_ms = (1000.0 / fps) * total_frames
        return elapsed_ms >= full_duration_ms

    def restarted(self, started_at_ms: int) -> "Animation":
        """New Animation over the same StateAssets, timeline reset."""
        return Animation(self._assets, started_at_ms)