from kungfu_chess.elo import elo_math


def test_expected_score_equal_ratings_is_one_half():
    assert elo_math.expected_score(1200, 1200) == 0.5


def test_expected_score_favors_the_higher_rated_player():
    higher = elo_math.expected_score(1400, 1200)
    lower = elo_math.expected_score(1200, 1400)
    assert higher > 0.5 > lower
    assert higher + lower == 1.0


def test_updated_rating_win_between_equal_ratings():
    assert elo_math.updated_rating(1200, 1200, actual_score=1.0) == 1216


def test_updated_rating_loss_between_equal_ratings():
    assert elo_math.updated_rating(1200, 1200, actual_score=0.0) == 1184


def test_updated_rating_draw_between_equal_ratings_is_unchanged():
    assert elo_math.updated_rating(1200, 1200, actual_score=0.5) == 1200


def test_updated_rating_draw_between_unequal_ratings_pulls_toward_each_other():
    higher_rated_draws = elo_math.updated_rating(1400, 1200, actual_score=0.5)
    lower_rated_draws = elo_math.updated_rating(1200, 1400, actual_score=0.5)
    assert higher_rated_draws == 1392
    assert lower_rated_draws == 1208


def test_updated_rating_upset_loss_costs_the_underdog_less():
    underdog_loses = elo_math.updated_rating(1200, 1400, actual_score=0.0)
    favorite_wins = elo_math.updated_rating(1400, 1200, actual_score=1.0)
    assert underdog_loses == 1192
    assert favorite_wins == 1408


def test_updated_rating_respects_a_custom_k_factor():
    assert elo_math.updated_rating(1500, 1500, actual_score=1.0, k_factor=16) == 1508