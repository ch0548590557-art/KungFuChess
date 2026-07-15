"""
AssetLoader: reads board.png, every piece's sprite frames, and every
piece's per-state config.json — once, at startup — and keeps all of it
in memory (Step 3's exit condition: "כל התמונות וההגדרות נטענות פעם
אחת בתחילת המשחק"). Nothing downstream (Animation, GameRenderer) ever
touches the filesystem again after AssetLoader.load() returns; they only
ever ask AssetLoader for an already-loaded StateAssets.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import kungfu_chess.config as config
from kungfu_chess.graphics.img import Img

ANIMATION_STATES: Tuple[str, ...] = ("idle", "move", "jump", "short_rest", "long_rest")

_SPRITE_FILENAME = re.compile(r"^(\d+)\.png$", re.IGNORECASE)


@dataclass(frozen=True)
class StateAssets:
    """Everything one (piece, state) pair's config.json + sprites/ folder
    contains, already parsed and already loaded into memory."""
    frames: Tuple[Img, ...]
    frames_per_sec: float
    is_loop: bool
    next_state: Optional[str]
    speed_m_per_sec: float


class AssetLoader:
    def __init__(self, assets_root: str | Path, cell_size_px: int = config.CELL_SIZE_PX,
                 piece_tokens: Optional[List[str]] = None,
                 states: Tuple[str, ...] = ANIMATION_STATES):
        self._root = Path(assets_root)
        self._cell_size_px = cell_size_px
        self._piece_tokens = piece_tokens if piece_tokens is not None else self._default_piece_tokens()
        self._states = states
        self._board: Optional[Img] = None
        self._loaded: Dict[Tuple[str, str], StateAssets] = {}

    # ---- public API -----------------------------------------------------

    def load(self, board_width_cells: int, board_height_cells: int) -> None:
        self._board = self._load_board(board_width_cells, board_height_cells)
        loaded: Dict[Tuple[str, str], StateAssets] = {}
        for token in self._piece_tokens:
            for state in self._states:
                loaded[(token, state)] = self._load_state(token, state)
        self._loaded = loaded

    def board(self) -> Img:
        if self._board is None:
            raise RuntimeError("AssetLoader.load(...) must be called before board()")
        return self._board

    def state_assets(self, token: str, state: str) -> StateAssets:
        try:
            return self._loaded[(token, state)]
        except KeyError:
            raise KeyError(
                f"No loaded assets for piece '{token}' / state '{state}'. "
                f"Was load() called? Known states: {self._states}"
            )

    @staticmethod
    def piece_token(color: str, kind: str) -> str:
        """('w','P') -> 'wP' - matches the assets/pieces/<token>/ folder
        naming already used by the shipped asset pack."""
        return f"{color}{kind}"

    # ---- internals --------------------------------------------------------

    @staticmethod
    def _default_piece_tokens() -> List[str]:
        return [
            AssetLoader.piece_token(color, kind)
            for color in sorted(config.VALID_COLORS)
            for kind in sorted(config.VALID_KINDS)
        ]

    def _load_board(self, width_cells: int, height_cells: int) -> Img:
        path = self._root / "board.png"
        target_size = (width_cells * self._cell_size_px, height_cells * self._cell_size_px)
        return Img().read(path, size=target_size)

    def _load_state(self, token: str, state: str) -> StateAssets:
        state_dir = self._root / "pieces" / token / "states" / state
        raw_config = self._read_config(state_dir / "config.json")
        graphics = raw_config.get("graphics", {})
        physics = raw_config.get("physics", {})
        return StateAssets(
            frames=tuple(self._load_sprites(state_dir / "sprites")),
            frames_per_sec=float(graphics.get("frames_per_sec", 1)),
            is_loop=bool(graphics.get("is_loop", True)),
            next_state=physics.get("next_state_when_finished"),
            speed_m_per_sec=float(physics.get("speed_m_per_sec", 0)),
        )

    def _read_config(self, path: Path) -> dict:
        if not path.is_file():
            raise FileNotFoundError(f"Missing animation config: {path}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_sprites(self, sprites_dir: Path) -> List[Img]:
        if not sprites_dir.is_dir():
            raise FileNotFoundError(f"Missing sprites folder: {sprites_dir}")

        numbered_files: List[Tuple[int, Path]] = []
        for file in sprites_dir.iterdir():
            match = _SPRITE_FILENAME.match(file.name)
            if match:
                numbered_files.append((int(match.group(1)), file))

        if not numbered_files:
            raise FileNotFoundError(f"No numbered *.png sprite frames found in {sprites_dir}")

        numbered_files.sort(key=lambda pair: pair[0])  # numeric, not lexicographic

        target_size = (self._cell_size_px, self._cell_size_px)
        return [
            Img().read(path, size=target_size, keep_aspect=True)
            for _, path in numbered_files
        ]