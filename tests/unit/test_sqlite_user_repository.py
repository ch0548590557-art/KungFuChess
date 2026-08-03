import pytest

from kungfu_chess.auth.sqlite_user_repository import SqliteUserRepository
from kungfu_chess.auth.user_repository import (
    UsernameAlreadyExistsError,
    UserNotFoundError,
)


def _repo() -> SqliteUserRepository:
    return SqliteUserRepository(":memory:")


def test_create_user_returns_user_with_default_rating():
    repo = _repo()

    user = repo.create_user("alice", b"hash", b"salt")

    assert user.id is not None
    assert user.username == "alice"
    assert user.password_hash == b"hash"
    assert user.salt == b"salt"
    assert user.rating == 1200
    assert user.created_at


def test_create_user_accepts_explicit_rating():
    repo = _repo()

    user = repo.create_user("bob", b"hash", b"salt", rating=1500)

    assert user.rating == 1500


def test_get_by_username_fetches_created_user():
    repo = _repo()
    created = repo.create_user("alice", b"hash", b"salt")

    fetched = repo.get_by_username("alice")

    assert fetched == created


def test_get_by_username_returns_none_when_missing():
    repo = _repo()

    assert repo.get_by_username("nobody") is None


def test_get_by_id_fetches_created_user():
    repo = _repo()
    created = repo.create_user("alice", b"hash", b"salt")

    fetched = repo.get_by_id(created.id)

    assert fetched == created


def test_get_by_id_returns_none_when_missing():
    repo = _repo()

    assert repo.get_by_id(999) is None


def test_create_user_with_duplicate_username_raises():
    repo = _repo()
    repo.create_user("alice", b"hash1", b"salt1")

    with pytest.raises(UsernameAlreadyExistsError):
        repo.create_user("alice", b"hash2", b"salt2")


def test_update_rating_changes_stored_value():
    repo = _repo()
    created = repo.create_user("alice", b"hash", b"salt")

    repo.update_rating(created.id, 1300)

    assert repo.get_by_id(created.id).rating == 1300


def test_update_rating_on_missing_user_raises():
    repo = _repo()

    with pytest.raises(UserNotFoundError):
        repo.update_rating(999, 1300)