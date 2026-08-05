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

WHY _read_password() RUNS getpass.getpass() IN A BACKGROUND THREAD WITH A
TIMEOUT, RATHER THAN A PLAIN try/except OR JUST input() (discovered live,
2026-08-05, confirmed against a real terminal before this was written):
getpass() does work correctly - confirmed manually in a real interactive
terminal, where it hid the password as typed and returned it correctly.
But on Windows it falls through to msvcrt.getwch(), which talks to the
real Win32 console API directly rather than sys.stdin - in a terminal
that doesn't host a genuine Win32 console (Git Bash/MinTTY being the
common case), that call doesn't raise anything at all, it just hangs
forever (confirmed directly: calling it alone with nothing feeding it
input never returns and never errors). A plain try/except is therefore
useless here - there is no exception to catch, only a call that may
never return. Bounding the wait in a background thread is the only way
to say "try the hidden-input path, but don't let it block forever if
it's not actually connected to anything." The timeout (a couple of
seconds) is not "give a human time to type" - it's "does this call even
respond at all" - a console that can receive input starts servicing
getwch() immediately whether or not a key has been pressed yet, so a
short bound is enough to tell working-but-waiting-for-a-keystroke apart
from not-connected-at-all.

WHY THE ABANDONED THREAD (ON TIMEOUT) ISN'T A CORRECTNESS RISK, BUT IS A
REAL, BOUNDED RESOURCE COST:
Not a correctness risk: if getpass() times out, that means nothing was
ever reaching it through the console API, so it can't "steal" keystrokes
the fallback input() reads from sys.stdin afterward - they were never
going to the same place. It IS a real cost though: the thread is daemon
(never blocks process exit - Python guarantees daemon threads are torn
down abruptly on interpreter shutdown, no join needed) but nothing can
ever cancel msvcrt.getwch() itself, so each timed-out call leaves one
thread permanently blocked for the rest of the process's life, holding
one OS thread + its default stack (~1MB on Windows). For a human
retrying a failed login a handful of times in one repl_client session
that's negligible; it would only matter for a caller that invoked this
in a tight loop many times within one long-running process, which
nothing in this codebase does.
"""

import queue
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from getpass import getpass

_VALID_ACTIONS = ("login", "register")

GETPASS_TIMEOUT_SECONDS = 2.5


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
        password = _read_password("password: ")
        return LoginCredentials(action=action, username=username, password=password)


def _read_password(prompt: str, timeout_seconds: float = GETPASS_TIMEOUT_SECONDS) -> str:
    """Tries getpass.getpass() (hidden input) with a bounded wait; falls
    back to plain, visible input() - with a printed warning - if getpass
    hasn't produced a result within timeout_seconds. See the module
    docstring for why a timeout, not a try/except, is what's needed here."""
    result: "queue.Queue" = queue.Queue(maxsize=1)

    def _try_getpass() -> None:
        try:
            result.put((True, getpass(prompt)))
        except Exception:
            result.put((False, ""))

    thread = threading.Thread(target=_try_getpass, daemon=True)
    thread.start()
    thread.join(timeout_seconds)

    if not thread.is_alive() and not result.empty():
        ok, value = result.get_nowait()
        if ok:
            return value

    print("\nWarning: could not hide password input on this terminal - it will be shown as you type.")
    return input(prompt)