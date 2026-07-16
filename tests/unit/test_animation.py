import pytest

from kungfu_chess.graphics.animation import Animation
from kungfu_chess.graphics.asset_loader import StateAssets
from kungfu_chess.graphics.img import Img


def _state_assets(frame_count=3, frames_per_sec=10.0, is_loop=True):
    frames = tuple(Img.blank(10, 10) for _ in range(frame_count))
    return StateAssets(frames=frames, frames_per_sec=frames_per_sec,
                        is_loop=is_loop, next_state=None, speed_m_per_sec=0.0)


def test_constructor_raises_when_state_assets_has_no_frames():
    empty_assets = _state_assets(frame_count=0)

    with pytest.raises(ValueError):
        Animation(empty_assets, started_at_ms=0)


def test_frame_index_at_the_start_moment_is_zero():
    animation = Animation(_state_assets(), started_at_ms=1000)

    assert animation.frame_index(now_ms=1000) == 0


def test_frame_index_advances_as_time_elapses():
    # fps=10 -> 100ms per frame; 150ms elapsed -> 1 whole frame has passed.
    animation = Animation(_state_assets(frame_count=3, frames_per_sec=10.0),
                           started_at_ms=0)

    assert animation.frame_index(now_ms=150) == 1


def test_frame_index_loops_back_to_zero_when_is_loop_is_true():
    # 3 frames, fps=10 -> 350ms elapsed is frame index 3, which loops to 0.
    animation = Animation(_state_assets(frame_count=3, frames_per_sec=10.0,
                                         is_loop=True), started_at_ms=0)

    assert animation.frame_index(now_ms=350) == 0


def test_frame_index_clamps_to_the_last_frame_when_not_looping():
    animation = Animation(_state_assets(frame_count=3, frames_per_sec=10.0,
                                         is_loop=False), started_at_ms=0)

    assert animation.frame_index(now_ms=10_000) == 2  # last of 3 frames


def test_frame_index_clamps_elapsed_time_to_zero_when_now_is_before_start():
    animation = Animation(_state_assets(), started_at_ms=1000)

    # A now_ms earlier than started_at_ms must never produce a negative
    # elapsed time - it should behave exactly like elapsed == 0.
    assert animation.frame_index(now_ms=500) == 0


def test_frame_index_holds_frame_zero_when_fps_is_zero():
    animation = Animation(_state_assets(frame_count=3, frames_per_sec=0.0),
                           started_at_ms=0)

    assert animation.frame_index(now_ms=5000) == 0


def test_frame_index_holds_frame_zero_when_there_is_only_one_frame():
    animation = Animation(_state_assets(frame_count=1, frames_per_sec=10.0),
                           started_at_ms=0)

    assert animation.frame_index(now_ms=5000) == 0


def test_current_frame_returns_the_exact_img_at_the_current_index():
    assets = _state_assets(frame_count=3, frames_per_sec=10.0)
    animation = Animation(assets, started_at_ms=0)

    assert animation.current_frame(now_ms=150) is assets.frames[1]


def test_is_finished_is_always_false_while_looping():
    animation = Animation(_state_assets(frame_count=3, frames_per_sec=10.0,
                                         is_loop=True), started_at_ms=0)

    assert animation.is_finished(now_ms=1_000_000) is False


def test_is_finished_false_before_the_full_duration_when_not_looping():
    # 3 frames, fps=10 -> full duration is 300ms.
    animation = Animation(_state_assets(frame_count=3, frames_per_sec=10.0,
                                         is_loop=False), started_at_ms=0)

    assert animation.is_finished(now_ms=299) is False


def test_is_finished_true_once_the_full_duration_has_elapsed_when_not_looping():
    animation = Animation(_state_assets(frame_count=3, frames_per_sec=10.0,
                                         is_loop=False), started_at_ms=0)

    assert animation.is_finished(now_ms=300) is True


def test_is_finished_true_immediately_when_fps_is_zero_and_not_looping():
    animation = Animation(_state_assets(frame_count=3, frames_per_sec=0.0,
                                         is_loop=False), started_at_ms=0)

    assert animation.is_finished(now_ms=0) is True


def test_restarted_keeps_the_same_assets_but_resets_the_timeline():
    assets = _state_assets(frame_count=3, frames_per_sec=10.0)
    original = Animation(assets, started_at_ms=0)

    restarted = original.restarted(started_at_ms=5000)

    assert restarted.state_assets is assets
    assert restarted.started_at_ms == 5000
    assert restarted.frame_index(now_ms=5000) == 0
