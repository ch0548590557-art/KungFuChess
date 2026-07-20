from kungfu_chess.graphics.img import Img
from kungfu_chess.graphics.move_log import MoveLog
from kungfu_chess.graphics.move_log_renderer import MoveLogRenderer


def _canvas(width=240, height=800):
    return Img.blank(width, height, color=(40, 40, 40, 255))


def test_draw_with_no_rows_does_not_raise():
    renderer = MoveLogRenderer()
    canvas = _canvas()
    log = MoveLog()

    renderer.draw(canvas, log, 'w', panel_x=12, top_y=100, bottom_y=canvas.height - 12)

    assert (canvas.width, canvas.height) == (240, 800)


def test_draw_with_a_few_rows_does_not_raise():
    renderer = MoveLogRenderer()
    canvas = _canvas()
    log = MoveLog()
    log.update([('w', 'e4', 2000), ('b', 'e5', 5000), ('w', 'Nf3', 8000)])

    renderer.draw(canvas, log, 'w', panel_x=12, top_y=100, bottom_y=canvas.height - 12)
    renderer.draw(canvas, log, 'b', panel_x=12, top_y=100, bottom_y=canvas.height - 12)

    assert (canvas.width, canvas.height) == (240, 800)


def test_draw_does_not_mutate_the_move_log_it_is_given():
    renderer = MoveLogRenderer()
    canvas = _canvas()
    log = MoveLog()
    log.update([('w', 'e4', 2000), ('w', 'Nf3', 8000)])
    rows_before = log.rows_for('w')

    renderer.draw(canvas, log, 'w', panel_x=12, top_y=100, bottom_y=canvas.height - 12)

    assert log.rows_for('w') == rows_before


def test_draw_with_more_rows_than_fit_does_not_raise_and_stays_within_the_panel():
    # 300 rows at the default row height would overflow a small panel
    # many times over - draw() must clip to what fits (auto-scroll to
    # the newest rows) rather than raise or draw past bottom_y.
    renderer = MoveLogRenderer(row_height_px=20)
    canvas = _canvas(width=240, height=200)  # deliberately short panel
    log = MoveLog()
    moves = [('w', f"m{i}", i * 1000) for i in range(300)]
    log.update(moves)

    renderer.draw(canvas, log, 'w', panel_x=12, top_y=20, bottom_y=canvas.height - 12)

    assert (canvas.width, canvas.height) == (240, 200)


def test_draw_with_a_panel_too_short_for_even_one_row_does_not_raise():
    renderer = MoveLogRenderer(row_height_px=20)
    canvas = _canvas(width=240, height=200)
    log = MoveLog()
    log.update([('w', 'e4', 2000)])

    # top_y right at bottom_y leaves zero room for any data row, only
    # the header/divider.
    renderer.draw(canvas, log, 'w', panel_x=12, top_y=canvas.height - 12, bottom_y=canvas.height - 12)

    assert (canvas.width, canvas.height) == (240, 200)
