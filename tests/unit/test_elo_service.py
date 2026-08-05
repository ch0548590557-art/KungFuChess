import os
import tempfile

import pytest

from kungfu_chess.elo.elo_service import EloService, UnknownPlayerError
from kungfu_chess.auth.sqlite_user_repository import SqliteUserRepository


def _repo() -> SqliteUserRepository:
    return SqliteUserRepository(":memory:")


def test_white_win_raises_white_and_lowers_black():
    repo = _repo()
    repo.create_user("alice", b"h", b"s", rating=1200)
    repo.create_user("bob", b"h", b"s", rating=1200)
    service = EloService(repo)

    service.record_game_result("alice", "bob", winner_color="w")

    assert repo.get_by_username("alice").rating == 1216
    assert repo.get_by_username("bob").rating == 1184


def test_black_win_raises_black_and_lowers_white():
    repo = _repo()
    repo.create_user("alice", b"h", b"s", rating=1200)
    repo.create_user("bob", b"h", b"s", rating=1200)
    service = EloService(repo)

    service.record_game_result("alice", "bob", winner_color="b")

    assert repo.get_by_username("alice").rating == 1184
    assert repo.get_by_username("bob").rating == 1216


def test_draw_between_unequal_ratings_pulls_toward_each_other():
    repo = _repo()
    repo.create_user("alice", b"h", b"s", rating=1400)
    repo.create_user("bob", b"h", b"s", rating=1200)
    service = EloService(repo)

    service.record_game_result("alice", "bob", winner_color=None)

    assert repo.get_by_username("alice").rating == 1392
    assert repo.get_by_username("bob").rating == 1208


def test_custom_k_factor_is_used_for_both_players():
    repo = _repo()
    repo.create_user("alice", b"h", b"s", rating=1500)
    repo.create_user("bob", b"h", b"s", rating=1500)
    service = EloService(repo, k_factor=16)

    service.record_game_result("alice", "bob", winner_color="w")

    assert repo.get_by_username("alice").rating == 1508
    assert repo.get_by_username("bob").rating == 1492


def test_unknown_white_username_raises():
    repo = _repo()
    repo.create_user("bob", b"h", b"s")
    service = EloService(repo)

    with pytest.raises(UnknownPlayerError) as exc_info:
        service.record_game_result("nobody", "bob", winner_color="w")
    assert exc_info.value.username == "nobody"


def test_unknown_black_username_raises():
    repo = _repo()
    repo.create_user("alice", b"h", b"s")
    service = EloService(repo)

    with pytest.raises(UnknownPlayerError) as exc_info:
        service.record_game_result("alice", "nobody", winner_color="w")
    assert exc_info.value.username == "nobody"


def test_invalid_winner_color_raises():
    repo = _repo()
    repo.create_user("alice", b"h", b"s")
    repo.create_user("bob", b"h", b"s")
    service = EloService(repo)

    with pytest.raises(ValueError):
        service.record_game_result("alice", "bob", winner_color="green")


def test_rating_updates_are_actually_persisted_to_the_database_file():
    """Explicit persistence check per the branch's requirement: reopen a
    fresh connection to the same on-disk file after record_game_result()
    returns, proving the new ratings survive past the in-process
    repository object, not just its in-memory User instances."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "users.sqlite3")
        repo = SqliteUserRepository(db_path)
        repo.create_user("alice", b"h", b"s", rating=1200)
        repo.create_user("bob", b"h", b"s", rating=1200)

        EloService(repo).record_game_result("alice", "bob", winner_color="w")
        repo.close()

        reopened = SqliteUserRepository(db_path)
        assert reopened.get_by_username("alice").rating == 1216
        assert reopened.get_by_username("bob").rating == 1184
        reopened.close()