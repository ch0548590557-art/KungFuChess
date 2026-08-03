"""
SqliteUserRepository: the (currently) only UserRepository implementation,
backed by a local SQLite file. Everything SQLite-specific (the schema,
the sqlite3 module, IntegrityError translation) lives only here - see
user_repository.py for why callers must never depend on any of that
directly.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from kungfu_chess.auth.user_repository import (
    User,
    UserRepository,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash BLOB NOT NULL,
    salt BLOB NOT NULL,
    rating INTEGER NOT NULL DEFAULT 1200,
    created_at TEXT NOT NULL
)
"""


class SqliteUserRepository(UserRepository):
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.execute(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def create_user(
        self,
        username: str,
        password_hash: bytes,
        salt: bytes,
        rating: int = 1200,
    ) -> User:
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._conn:
                cursor = self._conn.execute(
                    "INSERT INTO users (username, password_hash, salt, rating, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (username, password_hash, salt, rating, created_at),
                )
        except sqlite3.IntegrityError as exc:
            raise UsernameAlreadyExistsError(username) from exc

        return User(
            id=cursor.lastrowid,
            username=username,
            password_hash=password_hash,
            salt=salt,
            rating=rating,
            created_at=created_at,
        )

    def get_by_username(self, username: str) -> Optional[User]:
        row = self._conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return self._row_to_user(row) if row is not None else None

    def get_by_id(self, user_id: int) -> Optional[User]:
        row = self._conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return self._row_to_user(row) if row is not None else None

    def update_rating(self, user_id: int, rating: int) -> None:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE users SET rating = ? WHERE id = ?", (rating, user_id)
            )
        if cursor.rowcount == 0:
            raise UserNotFoundError(user_id)

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            salt=row["salt"],
            rating=row["rating"],
            created_at=row["created_at"],
        )