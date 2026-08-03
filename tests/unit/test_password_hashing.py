import sqlite3
import tempfile
import os

import pytest

from kungfu_chess.auth import password_hashing as ph
from kungfu_chess.auth.sqlite_user_repository import SqliteUserRepository


def test_verify_password_accepts_correct_password():
    salt = ph.generate_salt()
    hashed = ph.hash_password("correct horse", salt)

    assert ph.verify_password("correct horse", salt, hashed) is True


def test_verify_password_rejects_wrong_password():
    salt = ph.generate_salt()
    hashed = ph.hash_password("correct horse", salt)

    assert ph.verify_password("wrong password", salt, hashed) is False


def test_different_salts_give_different_hashes_for_same_password():
    salt_a = ph.generate_salt()
    salt_b = ph.generate_salt()

    assert salt_a != salt_b
    assert ph.hash_password("same password", salt_a) != ph.hash_password("same password", salt_b)


def test_generate_salt_returns_unique_values():
    assert ph.generate_salt() != ph.generate_salt()


def test_hash_password_raises_loudly_when_pepper_env_var_missing(monkeypatch):
    monkeypatch.delenv(ph.PEPPER_ENV_VAR, raising=False)
    salt = ph.generate_salt()

    with pytest.raises(RuntimeError, match=ph.PEPPER_ENV_VAR):
        ph.hash_password("anything", salt)


def test_different_pepper_gives_different_hash_for_same_password_and_salt(monkeypatch):
    salt = ph.generate_salt()

    monkeypatch.setenv(ph.PEPPER_ENV_VAR, "pepper-one")
    hash_with_pepper_one = ph.hash_password("same password", salt)

    monkeypatch.setenv(ph.PEPPER_ENV_VAR, "pepper-two")
    hash_with_pepper_two = ph.hash_password("same password", salt)

    assert hash_with_pepper_one != hash_with_pepper_two


def test_pepper_is_never_persisted_to_the_database():
    """Explicit check per the branch's security requirement: the pepper
    must never end up in the DB - not in a column, not in the schema, not
    anywhere in the file - since a stolen DB alone must not be enough to
    verify passwords."""
    pepper_value = os.environ[ph.PEPPER_ENV_VAR]

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "users.sqlite3")
        repo = SqliteUserRepository(db_path)

        salt = ph.generate_salt()
        hashed = ph.hash_password("hunter2", salt)
        repo.create_user("alice", hashed, salt)
        repo.close()

        conn = sqlite3.connect(db_path)
        try:
            full_dump = "\n".join(conn.iterdump())
        finally:
            conn.close()

        assert pepper_value not in full_dump
        assert "pepper" not in full_dump.lower()

        with open(db_path, "rb") as f:
            raw_bytes = f.read()
        assert pepper_value.encode("utf-8") not in raw_bytes