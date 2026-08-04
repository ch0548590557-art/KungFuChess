import pytest

from kungfu_chess.network.login_prompt import LoginCredentials, LoginPrompt, ShellLoginPrompt


def test_login_prompt_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        LoginPrompt()


def test_shell_login_prompt_reads_action_username_and_password(monkeypatch):
    answers = iter(["login", "  chani  "])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("kungfu_chess.network.login_prompt.getpass", lambda prompt="": "secret")

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials == LoginCredentials(action="login", username="chani", password="secret")


def test_shell_login_prompt_accepts_register_action(monkeypatch):
    answers = iter(["register", "chani"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("kungfu_chess.network.login_prompt.getpass", lambda prompt="": "secret")

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.action == "register"


def test_shell_login_prompt_normalizes_action_case_and_whitespace(monkeypatch):
    answers = iter(["  LOGIN  ", "chani"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("kungfu_chess.network.login_prompt.getpass", lambda prompt="": "secret")

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.action == "login"


def test_shell_login_prompt_reprompts_until_a_valid_action_is_given(monkeypatch):
    answers = iter(["banana", "still not it", "register", "chani"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("kungfu_chess.network.login_prompt.getpass", lambda prompt="": "secret")

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.action == "register"
    assert credentials.username == "chani"


def test_shell_login_prompt_passes_a_prompt_string_to_getpass(monkeypatch):
    seen = []

    def fake_getpass(prompt=""):
        seen.append(prompt)
        return "secret"

    answers = iter(["login", "chani"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("kungfu_chess.network.login_prompt.getpass", fake_getpass)

    ShellLoginPrompt().get_credentials()

    assert seen and "password" in seen[0].lower()