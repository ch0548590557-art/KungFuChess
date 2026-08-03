import pytest

from kungfu_chess.auth import password_hashing as ph


@pytest.fixture(autouse=True)
def _password_pepper(monkeypatch):
    """Every test that exercises real login/auth (AuthService, login_gate,
    ws_server, client_core) now goes through actual password hashing,
    which refuses to run without KUNGFU_CHESS_PASSWORD_PEPPER set (see
    auth/password_hashing.py) - one autouse fixture here is simpler than
    repeating monkeypatch.setenv in every test module that happens to
    touch auth, directly or transitively via WebSocketServer."""
    monkeypatch.setenv(ph.PEPPER_ENV_VAR, "test-suite-pepper-do-not-use-in-prod")