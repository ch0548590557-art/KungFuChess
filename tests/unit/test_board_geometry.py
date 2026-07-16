from kungfu_chess.graphics.board_geometry import BoardGeometry


def test_cell_to_pixel_uses_x_equals_col_and_y_equals_row():
    geometry = BoardGeometry(cell_size_px=100)

    x, y = geometry.cell_to_pixel(row=2, col=5)

    assert (x, y) == (500, 200)


def test_pixel_to_cell_is_inverse_of_cell_to_pixel():
    geometry = BoardGeometry(cell_size_px=100)

    x, y = geometry.cell_to_pixel(row=3, col=1)
    row, col = geometry.pixel_to_cell(x, y)

    assert (row, col) == (3, 1)


def test_interpolated_pixel_at_progress_zero_is_the_source_cell():
    geometry = BoardGeometry(cell_size_px=100)

    x, y = geometry.interpolated_pixel(src_row=0, src_col=0,
                                        dst_row=4, dst_col=4, progress=0.0)

    assert (x, y) == geometry.cell_to_pixel(0, 0)


def test_interpolated_pixel_at_progress_one_is_the_destination_cell():
    geometry = BoardGeometry(cell_size_px=100)

    x, y = geometry.interpolated_pixel(src_row=0, src_col=0,
                                        dst_row=4, dst_col=4, progress=1.0)

    assert (x, y) == geometry.cell_to_pixel(4, 4)


def test_interpolated_pixel_at_half_progress_is_the_midpoint():
    geometry = BoardGeometry(cell_size_px=100)

    x, y = geometry.interpolated_pixel(src_row=0, src_col=0,
                                        dst_row=2, dst_col=0, progress=0.5)

    assert (x, y) == (0, 100)


def test_interpolated_pixel_clamps_negative_progress_to_source():
    geometry = BoardGeometry(cell_size_px=100)

    x, y = geometry.interpolated_pixel(src_row=1, src_col=1,
                                        dst_row=3, dst_col=3, progress=-0.5)

    assert (x, y) == geometry.cell_to_pixel(1, 1)


def test_interpolated_pixel_clamps_progress_above_one_to_destination():
    geometry = BoardGeometry(cell_size_px=100)

    x, y = geometry.interpolated_pixel(src_row=1, src_col=1,
                                        dst_row=3, dst_col=3, progress=1.5)

    assert (x, y) == geometry.cell_to_pixel(3, 3)
