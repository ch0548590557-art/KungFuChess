"""
LoginPrompt: the interface ClientCore uses to obtain everything it needs
to identify itself to the server, without knowing or caring how it was
collected. Per this branch's own architecture decision, ClientCore must
never call input()/getpass() (or anything terminal-specific) directly -
only ever LoginPrompt.get_credentials() - so a future GUI only needs a
new LoginPrompt implementation (e.g. GuiLoginPrompt), never a ClientCore
change.

WHY get_credentials() REPLACED get_username() (feature/auth-sqlite-elo,
Step 4):
The placeholder identity step (username only, no password, no DB) from
feature/home-screen-basic-login is gone now that a real AuthService
backs login - a client must choose register vs. login and supply a
password, not just a display name. Widening the same single abstract
method (rather than adding separate get_password()/get_action() calls)
keeps "collecting credentials" one atomic prompt-side operation - a GUI
implementation can show one form and return one result, instead of
ClientCore orchestrating three separate round-trips to whatever UI is
behind this interface.

WHY LoginCredentials IS A DATACLASS RATHER THAN A (str, str, str) TUPLE:
Same reasoning as protocol.py's dedicated dataclasses over raw
containers - three same-typed strings in a tuple would be positional and
easy to transpose (action/username/password) with no error until a wrong
Error reason comes back from the server.

WHY ShellLoginPrompt USES getpass.getpass() FOR THE PASSWORD BUT input()
FOR EVERYTHING ELSE:
getpass() suppresses terminal echo so a password typed at this prompt
never appears on screen or ends up in shell scrollback - ordinary input()
has no such option. Both are still safe to call directly here for the
same reason plain input() was safe in the username-only version of this
file: get_credentials() runs synchronously from
ClientCore.prepare_login(), called before connect() starts anything
concurrent (see client_core.py's own note on why this differs from
repl_client's command loop, which had to move off input() entirely).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from getpass import getpass

_VALID_ACTIONS = ("login", "register")


@dataclass
class LoginCredentials:
    action: str  # "login" | "register"
    username: str
    password: str


class LoginPrompt(ABC):
    @abstractmethod
    def get_credentials(self) -> LoginCredentials:
        ...


class ShellLoginPrompt(LoginPrompt):
    def get_credentials(self) -> LoginCredentials:
        action = input("login or register? [login/register]: ").strip().lower()
        while action not in _VALID_ACTIONS:
            action = input("please type 'login' or 'register': ").strip().lower()
        username = input("username: ").strip()
        password = getpass("password: ")
        return LoginCredentials(action=action, username=username, password=password)