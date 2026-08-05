import pytest

from kungfu_chess.network.login_prompt import LoginCredentials, LoginPrompt, ShellLoginPrompt


def test_login_prompt_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        LoginPrompt()


def test_shell_login_prompt_reads_action_username_and_password(monkeypatch):
    answers = iter(["login", "  chani  ", "secret"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials == LoginCredentials(action="login", username="chani", password="secret")


def test_shell_login_prompt_accepts_register_action(monkeypatch):
    answers = iter(["register", "chani", "secret"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.action == "register"


def test_shell_login_prompt_normalizes_action_case_and_whitespace(monkeypatch):
    answers = iter(["  LOGIN  ", "chani", "secret"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.action == "login"


def test_shell_login_prompt_reprompts_until_a_valid_action_is_given(monkeypatch):
    answers = iter(["banana", "still not it", "register", "chani", "secret"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.action == "register"
    assert credentials.username == "chani"


def test_shell_login_prompt_does_not_strip_the_password(monkeypatch):
    """Unlike username/action, a password is taken verbatim - stripping
    it would silently reject any password with meaningful leading/
    trailing whitespace instead of just passing it through to the server
    to accept or reject."""
    answers = iter(["login", "chani", "  secret with spaces  "])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.password == "  secret with spaces  "


def test_shell_login_prompt_uses_plain_input_for_the_password_prompt(monkeypatch):
    """Regression test: getpass.getpass() was tried first and found to
    hang indefinitely with no error in terminals that don't host a real
    Win32 console (e.g. Git Bash/MinTTY) - see the module docstring.
    get_credentials() must go through builtins.input for every prompt,
    including the password, never getpass."""
    seen_prompts = []

    def fake_input(prompt=""):
        seen_prompts.append(prompt)
        answers = ["login", "chani", "secret"]
        return answers[len(seen_prompts) - 1]

    monkeypatch.setattr("builtins.input", fake_input)

    credentials = ShellLoginPrompt().get_credentials()

    assert credentials.password == "secret"
    assert any("password" in p.lower() for p in seen_prompts)