import threading

import pytest

from kungfu_chess.network.login_prompt import (
    LoginCredentials,
    LoginPrompt,
    ShellLoginPrompt,
    _read_password,
)


def _mock_getpass(monkeypatch, value):
    monkeypatch.setattr("kungfu_chess.network.login_prompt.getpass", lambda prompt="": value)


def test_login_prompt_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        LoginPrompt()


def test_shell_login_prompt_reads_action_username_and_password(monkeypatch):
    answers = iter(["login", "  chani  "])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    _mock_getpass(monkeypatch, "secret")

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials == LoginCredentials(action="login", username="chani", password="secret")


def test_shell_login_prompt_accepts_register_action(monkeypatch):
    answers = iter(["register", "chani"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    _mock_getpass(monkeypatch, "secret")

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.action == "register"


def test_shell_login_prompt_normalizes_action_case_and_whitespace(monkeypatch):
    answers = iter(["  LOGIN  ", "chani"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    _mock_getpass(monkeypatch, "secret")

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.action == "login"


def test_shell_login_prompt_reprompts_until_a_valid_action_is_given(monkeypatch):
    answers = iter(["banana", "still not it", "register", "chani"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    _mock_getpass(monkeypatch, "secret")

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.action == "register"
    assert credentials.username == "chani"


def test_shell_login_prompt_does_not_alter_the_password(monkeypatch):
    """Unlike username/action, a password is taken verbatim - stripping
    or otherwise touching it would silently reject any password with
    meaningful leading/trailing whitespace instead of just passing it
    through to the server to accept or reject."""
    answers = iter(["login", "chani"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    _mock_getpass(monkeypatch, "  secret with spaces  ")

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.password == "  secret with spaces  "


def test_shell_login_prompt_gets_the_password_via_read_password(monkeypatch):
    """get_credentials() must go through _read_password() (the
    getpass-with-timeout-fallback wrapper), not getpass()/input()
    directly - that wrapper is what gives a real terminal hidden input
    while keeping console-less environments from hanging forever."""
    answers = iter(["login", "chani"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(
        "kungfu_chess.network.login_prompt._read_password",
        lambda prompt: "secret-via-read-password",
    )

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.password == "secret-via-read-password"


# ---- _read_password(): getpass with a bounded fallback --------------------

def test_read_password_returns_the_getpass_value_when_it_responds_in_time(monkeypatch):
    monkeypatch.setattr("kungfu_chess.network.login_prompt.getpass", lambda prompt="": "hunter2")
    monkeypatch.setattr(
        "builtins.input", lambda prompt="": pytest.fail("must not fall back to input()")
    )

    assert _read_password("password: ", timeout_seconds=1.0) == "hunter2"


def test_read_password_falls_back_to_input_when_getpass_never_returns(monkeypatch, capsys):
    """Simulates the real bug found on Windows in a console-less terminal:
    getpass() hangs forever with no exception. _read_password() must
    still return promptly, bounded by timeout_seconds, via plain input() -
    with a warning explaining the password will be visible."""
    never_set = threading.Event()

    def _hanging_getpass(prompt=""):
        never_set.wait()  # blocks for the rest of the process's life
        return "unreachable"

    monkeypatch.setattr("kungfu_chess.network.login_prompt.getpass", _hanging_getpass)
    monkeypatch.setattr("builtins.input", lambda prompt="": "visible-fallback")

    value = _read_password("password: ", timeout_seconds=0.1)

    assert value == "visible-fallback"
    assert "Warning" in capsys.readouterr().out


def test_read_password_raising_also_falls_back_to_input(monkeypatch, capsys):
    """Belt-and-suspenders: if getpass() raises instead of hanging (a
    real exception, e.g. some other platform's GetPassWarning path),
    that must fall back exactly the same way as a timeout does."""
    def _broken_getpass(prompt=""):
        raise RuntimeError("no console")

    monkeypatch.setattr("kungfu_chess.network.login_prompt.getpass", _broken_getpass)
    monkeypatch.setattr("builtins.input", lambda prompt="": "visible-fallback")

    value = _read_password("password: ", timeout_seconds=1.0)

    assert value == "visible-fallback"
    assert "Warning" in capsys.readouterr().out


def test_repeated_getpass_timeouts_never_hang_the_process(monkeypatch):
    """Multiple failed/timed-out attempts (e.g. a user retrying a
    rejected login) each abandon one background thread - a real, bounded
    cost (see module docstring), not a leak beyond process lifetime. What
    must never happen is any of them blocking process/test exit - this
    test completing at all, rather than hanging the suite, is the proof;
    the thread-count/daemon assertions below just make that concrete."""
    never_set = threading.Event()

    def _hanging_getpass(prompt=""):
        never_set.wait()
        return "unreachable"

    monkeypatch.setattr("kungfu_chess.network.login_prompt.getpass", _hanging_getpass)
    monkeypatch.setattr("builtins.input", lambda prompt="": "fallback")

    before = set(threading.enumerate())
    for _ in range(3):
        assert _read_password("password: ", timeout_seconds=0.1) == "fallback"
    after = set(threading.enumerate())

    new_threads = after - before
    assert len(new_threads) == 3
    assert all(t.daemon for t in new_threads)