import json
import shutil

import pytest

from kungfu_chess.graphics.asset_loader import AssetLoader
from kungfu_chess.graphics.img import Img

_REAL_ASSETS_ROOT = "assets"
_BOARD_PNG = "assets/board.png"
_SQUARE_SPRITE = "assets/pieces/wP/states/idle/sprites/1.png"


def _write_state(states_dir, frame_paths, frames_per_sec=1, is_loop=True,
                  next_state=None, speed_m_per_sec=0):
    sprites_dir = states_dir / "sprites"
    sprites_dir.mkdir(parents=True)
    for name, source in frame_paths.items():
        shutil.copy(source, sprites_dir / name)

    config = {
        "physics": {"speed_m_per_sec": speed_m_per_sec,
                    "next_state_when_finished": next_state},
        "graphics": {"frames_per_sec": frames_per_sec, "is_loop": is_loop},
    }
    (states_dir / "config.json").write_text(json.dumps(config))


def test_piece_token_combines_color_and_kind():
    assert AssetLoader.piece_token("w", "P") == "wP"


def test_board_raises_before_load_is_called():
    loader = AssetLoader(_REAL_ASSETS_ROOT, piece_tokens=["wP"], states=("idle",))

    with pytest.raises(RuntimeError):
        loader.board()


def test_state_assets_raises_key_error_before_load_is_called():
    loader = AssetLoader(_REAL_ASSETS_ROOT, piece_tokens=["wP"], states=("idle",))

    with pytest.raises(KeyError):
        loader.state_assets("wP", "idle")


def test_load_returns_a_board_sized_to_cells_times_cell_size():
    loader = AssetLoader(_REAL_ASSETS_ROOT, cell_size_px=100,
                          piece_tokens=["wP"], states=("idle",))

    loader.load(board_width_cells=8, board_height_cells=8)

    assert (loader.board().width, loader.board().height) == (800, 800)


def test_load_reads_the_real_shipped_state_assets_correctly():
    loader = AssetLoader(_REAL_ASSETS_ROOT, piece_tokens=["wP"], states=("idle",))

    loader.load(board_width_cells=8, board_height_cells=8)
    state_assets = loader.state_assets("wP", "idle")

    # These values mirror assets/pieces/wP/states/idle/config.json - if
    # this test breaks, either the shipped config.json changed or
    # AssetLoader stopped reading it correctly.
    assert len(state_assets.frames) == 5
    assert state_assets.frames_per_sec == 4.0
    assert state_assets.is_loop is True
    assert state_assets.next_state == "idle"


def test_state_assets_raises_key_error_for_an_unknown_state(tmp_path):
    shutil.copy(_BOARD_PNG, tmp_path / "board.png")
    loader = AssetLoader(tmp_path, piece_tokens=["xX"], states=("idle",))
    _write_state(tmp_path / "pieces" / "xX" / "states" / "idle",
                  {"1.png": _SQUARE_SPRITE})

    loader.load(board_width_cells=1, board_height_cells=1)

    with pytest.raises(KeyError):
        loader.state_assets("xX", "move")  # never loaded - not in `states`


def test_load_raises_file_not_found_when_config_json_is_missing(tmp_path):
    shutil.copy(_BOARD_PNG, tmp_path / "board.png")
    # A states/idle/ folder that only has sprites/, no config.json.
    sprites_dir = tmp_path / "pieces" / "xX" / "states" / "idle" / "sprites"
    sprites_dir.mkdir(parents=True)
    shutil.copy(_SQUARE_SPRITE, sprites_dir / "1.png")

    loader = AssetLoader(tmp_path, piece_tokens=["xX"], states=("idle",))

    with pytest.raises(FileNotFoundError):
        loader.load(board_width_cells=1, board_height_cells=1)


def test_load_raises_file_not_found_when_sprites_folder_is_missing(tmp_path):
    shutil.copy(_BOARD_PNG, tmp_path / "board.png")
    states_dir = tmp_path / "pieces" / "xX" / "states" / "idle"
    states_dir.mkdir(parents=True)
    (states_dir / "config.json").write_text(json.dumps(
        {"physics": {}, "graphics": {}}))
    # sprites/ deliberately not created.

    loader = AssetLoader(tmp_path, piece_tokens=["xX"], states=("idle",))

    with pytest.raises(FileNotFoundError):
        loader.load(board_width_cells=1, board_height_cells=1)


def test_load_raises_file_not_found_when_no_numbered_sprites_exist(tmp_path):
    shutil.copy(_BOARD_PNG, tmp_path / "board.png")
    states_dir = tmp_path / "pieces" / "xX" / "states" / "idle"
    sprites_dir = states_dir / "sprites"
    sprites_dir.mkdir(parents=True)
    shutil.copy(_SQUARE_SPRITE, sprites_dir / "not_a_number.png")  # wrong name pattern
    (states_dir / "config.json").write_text(json.dumps(
        {"physics": {}, "graphics": {}}))

    loader = AssetLoader(tmp_path, piece_tokens=["xX"], states=("idle",))

    with pytest.raises(FileNotFoundError):
        loader.load(board_width_cells=1, board_height_cells=1)


def test_sprite_frames_are_sorted_numerically_not_lexicographically(tmp_path):
    shutil.copy(_BOARD_PNG, tmp_path / "board.png")
    states_dir = tmp_path / "pieces" / "xX" / "states" / "idle"
    # board.png (822x828, not square) and the shipped wP sprite (320x320,
    # perfectly square) resize to different final dimensions under
    # keep_aspect=True - that difference is how the test tells the two
    # frames apart without reading pixel data directly.
    _write_state(states_dir, {"2.png": _BOARD_PNG, "10.png": _SQUARE_SPRITE})

    loader = AssetLoader(tmp_path, cell_size_px=100,
                          piece_tokens=["xX"], states=("idle",))
    loader.load(board_width_cells=1, board_height_cells=1)
    frames = loader.state_assets("xX", "idle").frames

    assert len(frames) == 2
    expected_first = Img().read(_BOARD_PNG, size=(100, 100), keep_aspect=True)
    expected_second = Img().read(_SQUARE_SPRITE, size=(100, 100), keep_aspect=True)
    assert (frames[0].width, frames[0].height) == (expected_first.width, expected_first.height)
    assert (frames[1].width, frames[1].height) == (expected_second.width, expected_second.height)
