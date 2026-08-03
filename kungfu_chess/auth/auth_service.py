"""
AuthService: the interface login_gate.py (and anything else that needs
"is this username+password real") talks to, without knowing anything
about UserRepository, password_hashing, or how a User row is stored.
Same reasoning as UserRepository itself (see its own module docstring):
naming the interface lets a future implementation (e.g. one backed by an
external identity provider) swap in without touching a caller.

WHY register()/authenticate() RAISE TYPED EXCEPTIONS (UsernameTakenError/
InvalidCredentialsError) CARRYING A .reason STRING, RATHER THAN RETURNING
A RESULT OBJECT:
login_gate.py already has an established pattern for this exact shape -
LoginFailed(reason) - so callers translate a caught exception straight
into a wire Error(reason=...) with no extra mapping step. Giving these
exceptions their own `.reason` attribute (matching login_gate.LoginFailed's)
means login_gate.py can do `raise LoginFailed(exc.reason) from exc`
without a lookup table pairing exception types to reason strings.

WHY authenticate() RAISES THE SAME InvalidCredentialsError WHETHER THE
USERNAME DOESN'T EXIST OR THE PASSWORD IS WRONG:
Returning a different reason for "no such user" vs. "wrong password"
would let a client enumerate which usernames are registered by watching
which error comes back - standard login-endpoint hygiene is to make
"unknown user" and "wrong password" indistinguishable from outside.
"""

from abc import ABC, abstractmethod

from kungfu_chess.auth import password_hashing
from kungfu_chess.auth.user_repository import User, UserRepository, UsernameAlreadyExistsError


class UsernameTakenError(Exception):
    def __init__(self, username: str):
        super().__init__(f"username already taken: {username}")
        self.username = username
        self.reason = "username_taken"


class InvalidCredentialsError(Exception):
    def __init__(self):
        super().__init__("invalid username or password")
        self.reason = "invalid_credentials"


class AuthService(ABC):
    @abstractmethod
    def register(self, username: str, password: str) -> User:
        """Raises UsernameTakenError if the username is already registered."""
        ...

    @abstractmethod
    def authenticate(self, username: str, password: str) -> User:
        """Raises InvalidCredentialsError if the username doesn't exist or
        the password doesn't match it."""
        ...


class SqliteAuthService(AuthService):
    """The only AuthService implementation so far. Named for the storage
    stack actually in use today (SqliteUserRepository) rather than for
    anything SQLite-specific in this class itself - it only ever talks to
    the UserRepository interface, so it would work unchanged against any
    other UserRepository implementation."""

    def __init__(self, user_repository: UserRepository):
        self._repository = user_repository

    def register(self, username: str, password: str) -> User:
        salt = password_hashing.generate_salt()
        hashed = password_hashing.hash_password(password, salt)
        try:
            return self._repository.create_user(username, hashed, salt)
        except UsernameAlreadyExistsError as exc:
            raise UsernameTakenError(username) from exc

    def authenticate(self, username: str, password: str) -> User:
        user = self._repository.get_by_username(username)
        if user is None:
            raise InvalidCredentialsError()
        if not password_hashing.verify_password(password, user.salt, user.password_hash):
            raise InvalidCredentialsError()
        return user