from kungfu_chess.model.board import Board
from kungfu_chess.model.position import Position
from kungfu_chess.input.board_mapper import BoardMapper


def test_x_0_to_99_maps_to_column_0():
    mapper = BoardMapper(Board(4, 4))
    assert mapper.pixel_to_cell(0, 0).col == 0
    assert mapper.pixel_to_cell(99, 0).col == 0


def test_x_100_to_199_maps_to_column_1():
    mapper = BoardMapper(Board(4, 4))
    assert mapper.pixel_to_cell(100, 0).col == 1
    assert mapper.pixel_to_cell(199, 0).col == 1


def test_y_100_to_199_maps_to_row_1():
    mapper = BoardMapper(Board(4, 4))
    assert mapper.pixel_to_cell(0, 100).row == 1


def test_outside_click_is_rejected():
    mapper = BoardMapper(Board(4, 4))
    assert mapper.pixel_to_cell(1000, 1000) is None
