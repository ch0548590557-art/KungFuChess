import pytest

from kungfu_chess.network.login_prompt import LoginPrompt, ShellLoginPrompt


def test_login_prompt_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        LoginPrompt()


def test_shell_login_prompt_reads_and_strips_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "  chani  ")
    assert ShellLoginPrompt().get_username() == "chani"


def test_shell_login_prompt_passes_a_prompt_string_to_input(monkeypatch):
    seen = []

    def fake_input(prompt=""):
        seen.append(prompt)
        return "chani"

    monkeypatch.setattr("builtins.input", fake_input)
    ShellLoginPrompt().get_username()

    assert seen and "username" in seen[0].lower()