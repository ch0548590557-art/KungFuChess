import pytest

from kungfu_chess.graphics.img import Img

_BOARD_PNG = "assets/board.png"


def test_blank_creates_an_image_with_the_requested_dimensions():
    img = Img.blank(width=120, height=80)

    assert (img.width, img.height) == (120, 80)


def test_width_and_height_raise_before_any_image_is_loaded():
    img = Img()

    with pytest.raises(ValueError):
        img.width
    with pytest.raises(ValueError):
        img.height


def test_read_raises_file_not_found_for_a_missing_path():
    with pytest.raises(FileNotFoundError):
        Img().read("assets/does_not_exist.png")


def test_read_resizes_to_the_requested_size():
    img = Img().read(_BOARD_PNG, size=(400, 400))

    assert (img.width, img.height) == (400, 400)


def test_read_with_keep_aspect_shrinks_to_fit_without_cropping():
    img = Img().read(_BOARD_PNG, size=(200, 1000), keep_aspect=True)

    # keep_aspect picks the *smaller* scale of the two axes, so neither
    # side ends up larger than what was asked for.
    assert img.width <= 200
    assert img.height <= 1000


def test_copy_is_independent_of_the_original():
    original = Img.blank(50, 50)
    duplicate = original.copy()

    duplicate.resize(10, 10)

    # resize() mutates in place - if copy() had shared the same
    # underlying image, the original would have shrunk too.
    assert (duplicate.width, duplicate.height) == (10, 10)
    assert (original.width, original.height) == (50, 50)


def test_resize_changes_width_and_height():
    img = Img.blank(50, 50)

    img.resize(100, 80)

    assert (img.width, img.height) == (100, 80)


def test_resize_with_keep_aspect_preserves_the_larger_target_bound():
    img = Img.blank(100, 50)  # 2:1 aspect ratio

    img.resize(60, 60, keep_aspect=True)

    assert img.width == 60
    assert img.height == 30


def test_draw_on_raises_when_the_sprite_does_not_fit_at_that_position():
    canvas = Img.blank(100, 100)
    sprite = Img.blank(50, 50)

    with pytest.raises(ValueError):
        sprite.draw_on(canvas, x=80, y=80)  # 80+50 > 100 on both axes


def test_draw_on_succeeds_within_bounds_and_leaves_canvas_size_unchanged():
    canvas = Img.blank(100, 100)
    sprite = Img.blank(50, 50)

    sprite.draw_on(canvas, x=0, y=0)

    assert (canvas.width, canvas.height) == (100, 100)


def test_draw_on_handles_mismatched_channel_counts_without_raising():
    # blank()'s default color is a 4-channel (BGRA) color; passing a
    # 3-length tuple produces a 3-channel (BGR) image instead. draw_on()
    # is documented to convert between them - this proves that branch
    # doesn't crash rather than leaving it unexercised.
    canvas = Img.blank(100, 100, color=(0, 0, 0))       # 3 channels
    sprite = Img.blank(20, 20, color=(0, 0, 0, 255))    # 4 channels

    sprite.draw_on(canvas, x=0, y=0)

    assert (canvas.width, canvas.height) == (100, 100)


def test_put_text_does_not_raise_and_leaves_dimensions_unchanged():
    canvas = Img.blank(200, 100)

    canvas.put_text("hi", 10, 50, font_size=1)

    assert (canvas.width, canvas.height) == (200, 100)


def test_fill_rect_does_not_raise_and_leaves_dimensions_unchanged():
    canvas = Img.blank(200, 100)

    canvas.fill_rect(10, 10, 50, 4, color=(255, 255, 255, 255))

    assert (canvas.width, canvas.height) == (200, 100)


def test_fill_rect_raises_before_any_image_is_loaded():
    with pytest.raises(ValueError):
        Img().fill_rect(0, 0, 10, 10)
