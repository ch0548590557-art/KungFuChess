import pytest

from kungfu_chess.auth.auth_service import (
    InvalidCredentialsError,
    SqliteAuthService,
    UsernameTakenError,
)
from kungfu_chess.auth.sqlite_user_repository import SqliteUserRepository


def _service() -> SqliteAuthService:
    return SqliteAuthService(SqliteUserRepository(":memory:"))


def test_register_creates_a_user_with_default_rating():
    service = _service()

    user = service.register("alice", "hunter2")

    assert user.username == "alice"
    assert user.rating == 1200


def test_register_then_authenticate_with_correct_password_succeeds():
    service = _service()
    registered = service.register("alice", "hunter2")

    authenticated = service.authenticate("alice", "hunter2")

    assert authenticated == registered


def test_register_with_duplicate_username_raises_username_taken():
    service = _service()
    service.register("alice", "hunter2")

    with pytest.raises(UsernameTakenError) as exc_info:
        service.register("alice", "different password")
    assert exc_info.value.reason == "username_taken"


def test_authenticate_with_wrong_password_raises_invalid_credentials():
    service = _service()
    service.register("alice", "hunter2")

    with pytest.raises(InvalidCredentialsError) as exc_info:
        service.authenticate("alice", "wrong password")
    assert exc_info.value.reason == "invalid_credentials"


def test_authenticate_with_unknown_username_raises_invalid_credentials():
    service = _service()

    with pytest.raises(InvalidCredentialsError) as exc_info:
        service.authenticate("nobody", "anything")
    assert exc_info.value.reason == "invalid_credentials"