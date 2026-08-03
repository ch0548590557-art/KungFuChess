"""
UserRepository: the interface every persistence-layer consumer (login,
registration, EloService) talks to for user records, without knowing or
caring which storage engine backs it. Per this branch's architecture
decision, swapping SQLite for another database later should mean writing
a new UserRepository implementation, never touching a caller.

WHY THIS IS AN ABC RATHER THAN A DUCK-TYPED CLASS (same reasoning as
network/login_prompt.py's LoginPrompt on the earlier branch):
naming the interface gives "the object that knows how to store/fetch
users" a stable name in signatures and test doubles.

WHY UsernameAlreadyExistsError AND UserNotFoundError LIVE HERE, NOT IN
THE SQLITE IMPLEMENTATION:
callers must be able to catch a stable, storage-agnostic exception type.
If SqliteUserRepository let sqlite3.IntegrityError escape directly, every
caller would be coupled to SQLite even though UserRepository itself
promises otherwise.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    id: int
    username: str
    password_hash: bytes
    salt: bytes
    rating: int
    created_at: str


class UsernameAlreadyExistsError(Exception):
    def __init__(self, username: str):
        super().__init__(f"username already exists: {username}")
        self.username = username


class UserNotFoundError(Exception):
    def __init__(self, user_id: int):
        super().__init__(f"no user with id: {user_id}")
        self.user_id = user_id


class UserRepository(ABC):
    @abstractmethod
    def create_user(
        self,
        username: str,
        password_hash: bytes,
        salt: bytes,
        rating: int = 1200,
    ) -> User:
        """Raises UsernameAlreadyExistsError if the username is taken."""
        ...

    @abstractmethod
    def get_by_username(self, username: str) -> Optional[User]:
        ...

    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[User]:
        ...

    @abstractmethod
    def update_rating(self, user_id: int, rating: int) -> None:
        """Raises UserNotFoundError if no user has this id."""
        ...