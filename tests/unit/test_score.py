from kungfu_chess.graphics.score import DEFAULT_POINT_VALUES, scores_from_captures


def test_no_captures_gives_zero_for_both_colors():
    assert scores_from_captures([]) == {'w': 0, 'b': 0}


def test_a_captured_black_pawn_awards_its_point_value_to_white():
    scores = scores_from_captures([('P', 'b')])

    assert scores == {'w': DEFAULT_POINT_VALUES['P'], 'b': 0}


def test_a_captured_white_queen_awards_its_point_value_to_black():
    scores = scores_from_captures([('Q', 'w')])

    assert scores == {'w': 0, 'b': DEFAULT_POINT_VALUES['Q']}


def test_multiple_captures_accumulate_per_color():
    captures = [('P', 'b'), ('N', 'b'), ('Q', 'w')]

    scores = scores_from_captures(captures)

    expected_white = DEFAULT_POINT_VALUES['P'] + DEFAULT_POINT_VALUES['N']
    assert scores == {'w': expected_white, 'b': DEFAULT_POINT_VALUES['Q']}


def test_king_capture_is_worth_zero_points():
    scores = scores_from_captures([('K', 'b')])

    assert scores == {'w': 0, 'b': 0}


def test_custom_point_values_override_the_defaults():
    scores = scores_from_captures([('P', 'b')], point_values={'P': 100})

    assert scores == {'w': 100, 'b': 0}


def test_an_unknown_kind_defaults_to_zero_points_instead_of_raising():
    scores = scores_from_captures([('?', 'b')])

    assert scores == {'w': 0, 'b': 0}
