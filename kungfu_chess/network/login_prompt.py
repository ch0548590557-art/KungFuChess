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

WHY ShellLoginPrompt USES PLAIN input() FOR THE PASSWORD TOO, NOT
getpass.getpass() (discovered live, 2026-08-05):
getpass() was tried first, for the usual reason (suppressing terminal
echo). On Windows, getpass falls through to msvcrt.getwch(), which talks
to the real Win32 console API directly rather than reading through
sys.stdin - in any terminal that doesn't host a genuine Win32 console
(Git Bash/MinTTY being the common case, but other terminal wrappers too),
that call doesn't raise, it just hangs forever waiting on a console that
was never connected to what the user is actually typing into - "can't
enter a password" with no error at all. repl_client.py is explicitly a
manual dev/playtesting tool (see its own module docstring), not a
security boundary - the actual secret-handling guarantee is server-side
(password_hashing.py's salt+pepper), so trading away local echo
suppression for "works in every terminal, no silent hangs" is the right
call here specifically, even though it wouldn't be for a production
login screen.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

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
        password = input("password: ")
        return LoginCredentials(action=action, username=username, password=password)