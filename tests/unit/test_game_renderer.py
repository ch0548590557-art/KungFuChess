import kungfu_chess.config as config
from kungfu_chess.engine.game_engine import GameSnapshot
from kungfu_chess.graphics.asset_loader import AssetLoader
from kungfu_chess.graphics.board_geometry import BoardGeometry
from kungfu_chess.graphics.game_renderer import GameRenderer

_ASSETS_ROOT = "assets"
_BOARD_CELLS = 8
_PANEL_WIDTH_PX = 240  # must match GameRenderer's own default


def _build_renderer(piece_tokens=("wP",), states=("idle", "move")):
    loader = AssetLoader(_ASSETS_ROOT, piece_tokens=list(piece_tokens), states=states)
    loader.load(_BOARD_CELLS, _BOARD_CELLS)
    geometry = BoardGeometry(cell_size_px=config.CELL_SIZE_PX)
    return GameRenderer(loader, geometry), loader


def _expected_canvas_size(loader):
    return (loader.board().width + 2 * _PANEL_WIDTH_PX, loader.board().height)


def _snapshot(pieces=(), motions=None, game_over=False, winner=None, captures=None,
               completed_moves=None):
    return GameSnapshot(board_width=_BOARD_CELLS, board_height=_BOARD_CELLS,
                         pieces=list(pieces), game_over=game_over, winner=winner,
                         motions=motions or {}, captures=captures,
                         completed_moves=completed_moves)


def test_render_with_no_pieces_returns_a_canvas_sized_to_the_board():
    renderer, loader = _build_renderer()

    canvas = renderer.render(_snapshot(), now_ms=0)

    assert (canvas.width, canvas.height) == _expected_canvas_size(loader)


def test_render_draws_an_idle_piece_without_raising():
    renderer, _ = _build_renderer()
    snapshot = _snapshot(pieces=[("P", "w", 0, 0, "IDLE")])

    canvas = renderer.render(snapshot, now_ms=0)

    assert (canvas.width, canvas.height) == (800 + 2 * _PANEL_WIDTH_PX, 800)


def test_render_skips_captured_pieces_entirely():
    # 'bQ' was never loaded (only 'wP' is) - if a CAPTURED piece weren't
    # skipped before its assets were looked up, this would raise KeyError.
    renderer, _ = _build_renderer()
    snapshot = _snapshot(pieces=[("Q", "b", 3, 3, "CAPTURED")])

    canvas = renderer.render(snapshot, now_ms=0)

    assert (canvas.width, canvas.height) == (800 + 2 * _PANEL_WIDTH_PX, 800)


def test_render_falls_back_to_idle_animation_for_an_unrecognized_engine_state():
    # Only 'idle'/'move' are loaded; a state outside the known
    # IDLE/MOVING/JUMPING set must resolve to "idle", not crash.
    renderer, _ = _build_renderer()
    snapshot = _snapshot(pieces=[("P", "w", 0, 0, "SOME_UNKNOWN_STATE")])

    canvas = renderer.render(snapshot, now_ms=0)

    assert (canvas.width, canvas.height) == (800 + 2 * _PANEL_WIDTH_PX, 800)


def test_render_handles_an_in_progress_motion_across_its_whole_timeline():
    renderer, _ = _build_renderer()
    motions = {(0, 0): (0, 2, 1000, 2000)}  # travelling (0,0) -> (0,2)
    snapshot = _snapshot(pieces=[("P", "w", 0, 0, "MOVING")], motions=motions)

    for now_ms in (1000, 1500, 2000, 2500):  # start, mid, arrival, past-arrival
        canvas = renderer.render(snapshot, now_ms=now_ms)
        assert (canvas.width, canvas.height) == (800 + 2 * _PANEL_WIDTH_PX, 800)


def test_render_handles_a_motion_whose_arrival_equals_its_start():
    # _progress()'s defensive branch (arrival_ms <= start_ms -> 1.0),
    # guarding against a division by zero.
    renderer, _ = _build_renderer()
    motions = {(0, 0): (0, 1, 500, 500)}
    snapshot = _snapshot(pieces=[("P", "w", 0, 0, "MOVING")], motions=motions)

    canvas = renderer.render(snapshot, now_ms=500)

    assert (canvas.width, canvas.height) == (800 + 2 * _PANEL_WIDTH_PX, 800)


def test_render_keeps_the_same_animation_object_across_calls_in_the_same_state():
    renderer, _ = _build_renderer()
    snapshot = _snapshot(pieces=[("P", "w", 0, 0, "IDLE")])

    renderer.render(snapshot, now_ms=0)
    first_animation = renderer._animations[(0, 0)]
    renderer.render(snapshot, now_ms=50)
    second_animation = renderer._animations[(0, 0)]

    # Re-creating the Animation every frame would reset its timeline
    # (started_at_ms) each time, so it would never visibly progress.
    assert first_animation is second_animation


def test_render_creates_a_new_animation_when_the_piece_state_changes():
    renderer, _ = _build_renderer()
    idle_snapshot = _snapshot(pieces=[("P", "w", 0, 0, "IDLE")])
    moving_snapshot = _snapshot(pieces=[("P", "w", 0, 0, "MOVING")],
                                 motions={(0, 0): (0, 1, 0, 1000)})

    renderer.render(idle_snapshot, now_ms=0)
    idle_animation = renderer._animations[(0, 0)]
    renderer.render(moving_snapshot, now_ms=100)
    moving_animation = renderer._animations[(0, 0)]

    assert idle_animation is not moving_animation


def test_render_forgets_stale_animations_once_a_cell_empties():
    renderer, _ = _build_renderer()
    occupied = _snapshot(pieces=[("P", "w", 0, 0, "IDLE")])
    empty = _snapshot(pieces=[])

    renderer.render(occupied, now_ms=0)
    assert (0, 0) in renderer._animations

    renderer.render(empty, now_ms=100)
    assert (0, 0) not in renderer._animations


def test_render_draws_a_game_over_overlay_without_raising():
    renderer, loader = _build_renderer()
    snapshot = _snapshot(pieces=[("P", "w", 0, 0, "IDLE")],
                          game_over=True, winner="w", captures=[("P", "b")])

    canvas = renderer.render(snapshot, now_ms=0)

    assert (canvas.width, canvas.height) == _expected_canvas_size(loader)


def test_render_game_over_overlay_works_for_both_winner_colors():
    renderer, _ = _build_renderer()

    for winner in ("w", "b"):
        snapshot = _snapshot(game_over=True, winner=winner, captures=[])
        canvas = renderer.render(snapshot, now_ms=0)
        assert (canvas.width, canvas.height) == (800 + 2 * _PANEL_WIDTH_PX, 800)


def test_render_game_over_overlay_tolerates_captures_being_none():
    # GameSnapshot.captures defaults to None (dataclass default) rather
    # than an empty list - the overlay must not crash on that default.
    renderer, _ = _build_renderer()
    snapshot = _snapshot(game_over=True, winner="w", captures=None)

    canvas = renderer.render(snapshot, now_ms=0)

    assert (canvas.width, canvas.height) == (800 + 2 * _PANEL_WIDTH_PX, 800)


def test_left_panel_width_px_matches_the_board_x_offset_used_by_render():
    renderer, loader = _build_renderer()

    canvas = renderer.render(_snapshot(), now_ms=0)

    assert renderer.left_panel_width_px == _PANEL_WIDTH_PX
    assert canvas.width == loader.board().width + 2 * renderer.left_panel_width_px


def test_score_panels_are_drawn_every_frame_even_without_game_over():
    # The whole point of this feature: panels are NOT gated behind
    # snapshot.game_over the way the winner banner is.
    renderer, _ = _build_renderer()
    snapshot = _snapshot(pieces=[("P", "w", 0, 0, "IDLE")],
                          game_over=False, captures=[("P", "b")])

    canvas = renderer.render(snapshot, now_ms=0)

    assert (canvas.width, canvas.height) == (800 + 2 * _PANEL_WIDTH_PX, 800)


def test_custom_panel_width_is_reflected_in_canvas_size_and_the_property():
    loader = AssetLoader(_ASSETS_ROOT, piece_tokens=["wP"], states=["idle", "move"])
    loader.load(_BOARD_CELLS, _BOARD_CELLS)
    geometry = BoardGeometry(cell_size_px=config.CELL_SIZE_PX)
    renderer = GameRenderer(loader, geometry, panel_width_px=80)

    canvas = renderer.render(_snapshot(), now_ms=0)

    assert renderer.left_panel_width_px == 80
    assert canvas.width == loader.board().width + 160


def test_render_with_completed_moves_being_none_does_not_raise():
    # GameSnapshot.completed_moves defaults to None (dataclass default),
    # same as captures - MoveLog.update must tolerate that defensively.
    renderer, _ = _build_renderer()
    snapshot = _snapshot(completed_moves=None)

    canvas = renderer.render(snapshot, now_ms=0)

    assert (canvas.width, canvas.height) == (800 + 2 * _PANEL_WIDTH_PX, 800)


def test_render_feeds_completed_moves_into_the_renderers_move_log():
    # Confirms the wiring: each render() call hands the snapshot's
    # completed_moves to the renderer's own persistent MoveLog, split
    # correctly per color - accessed the same way existing tests already
    # reach into renderer._animations to prove internal wiring.
    renderer, _ = _build_renderer()
    completed_moves = [('w', 'e4', 2000), ('b', 'e5', 5000), ('w', 'Nf3', 8000)]
    snapshot = _snapshot(completed_moves=completed_moves)

    renderer.render(snapshot, now_ms=0)

    assert renderer._move_log.rows_for('w') == [("00:02.000", "e4"), ("00:08.000", "Nf3")]
    assert renderer._move_log.rows_for('b') == [("00:05.000", "e5")]


def test_render_across_multiple_frames_incrementally_grows_the_move_log_without_duplicates():
    renderer, _ = _build_renderer()

    renderer.render(_snapshot(completed_moves=[('w', 'e4', 2000)]), now_ms=0)
    renderer.render(_snapshot(completed_moves=[('w', 'e4', 2000), ('b', 'e5', 5000)]), now_ms=100)

    assert renderer._move_log.rows_for('w') == [("00:02.000", "e4")]
    assert renderer._move_log.rows_for('b') == [("00:05.000", "e5")]


def test_render_with_many_completed_moves_does_not_raise():
    # Exercises MoveLogRenderer's auto-scroll-to-latest path (more rows
    # than the panel can show) through the full GameRenderer.render()
    # path, not just MoveLogRenderer in isolation.
    renderer, _ = _build_renderer()
    completed_moves = [('w' if i % 2 == 0 else 'b', 'Nf3', i * 1000) for i in range(100)]
    snapshot = _snapshot(completed_moves=completed_moves)

    canvas = renderer.render(snapshot, now_ms=0)

    assert (canvas.width, canvas.height) == (800 + 2 * _PANEL_WIDTH_PX, 800)


def test_render_with_game_still_ongoing_does_not_raise():
    # Img exposes no pixel-read API, so this can't directly prove the
    # overlay branch was skipped - only that the ordinary, game_over=False
    # path (the overwhelming majority of frames) still renders cleanly
    # now that _draw_game_over_overlay exists as a possible extra step.
    renderer, _ = _build_renderer()
    snapshot = _snapshot(pieces=[("P", "w", 0, 0, "IDLE")],
                          game_over=False, winner=None, captures=[])

    canvas = renderer.render(snapshot, now_ms=0)

    assert (canvas.width, canvas.height) == (800 + 2 * _PANEL_WIDTH_PX, 800)
