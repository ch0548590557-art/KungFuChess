"""
LoginPrompt: the interface ClientCore uses to obtain a username, without
knowing or caring how it was collected. Per this branch's own
architecture decision: ClientCore must never call input() (or anything
terminal-specific) directly - only ever LoginPrompt.get_username() - so
a future GUI only needs a new LoginPrompt implementation (e.g.
GuiLoginPrompt), never a ClientCore change.

WHY THIS IS AN ABC RATHER THAN A PLAIN CALLABLE (Callable[[], str]):
A single-abstract-method interface behaves the same as a callable in
practice, but naming it (LoginPrompt, get_username) gives the concept a
stable name in signatures, docstrings, and test doubles - "the object
that knows how to ask for a username" reads clearer at every call site
than an anonymous function type would.

WHY ShellLoginPrompt's input() IS SAFE HERE, UNLIKE repl_client's OWN
COMMAND-READING LOOP:
repl_client._read_command() had to move off input() to
sys.stdin.readline() because it runs from a background thread
(run_in_executor) while an asyncio event loop is already running on the
main thread - CPython's input() raises `RuntimeError: lost sys.stdin`
in that situation (discovered live, Step 5 of the previous branch).
ClientCore.prepare_login() runs synchronously, called before
connect() ever starts anything concurrent (see client_core.py) - plain
input() on the main thread is exactly its ordinary, safe use case.
"""

from abc import ABC, abstractmethod


class LoginPrompt(ABC):
    @abstractmethod
    def get_username(self) -> str:
        ...


class ShellLoginPrompt(LoginPrompt):
    def get_username(self) -> str:
        return input("username: ").strip()