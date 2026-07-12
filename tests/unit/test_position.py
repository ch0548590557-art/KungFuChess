from kungfu_chess.model.position import Position


def test_equal_positions():
    assert Position(2, 3) == Position(2, 3)


def test_different_positions_not_equal():
    assert Position(2, 3) != Position(2, 4)
    assert Position(2, 3) != Position(3, 3)


def test_position_is_hashable():
    assert Position(1, 1) in {Position(1, 1), Position(2, 2)}


def test_readable_repr():
    assert repr(Position(1, 2)) == "Position(row=1, col=2)"
