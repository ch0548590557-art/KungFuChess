"""
repl_client: a minimal interactive terminal client for manually
playtesting the WS transport end-to-end (Step 5). Connects via
ClientCore, prints the board as text after every update, and reads
"move <r>,<c> <r>,<c>" / "jump <r>,<c>" / "quit" from stdin.

Not a real game client - no graphics, no algebraic notation. It exists
purely so a human can drive two independent terminal processes against
the same WebSocketServer and watch a real game play out, proving the
whole stack (protocol -> SessionManager -> GameSession -> GameEngine ->
RealTimeArbiter's tick-driven arrivals) works end to end. A real UI is
later work, on top of this same ClientCore.

WHY A USERNAME IS COLLECTED VIA ShellLoginPrompt BEFORE connect()
(feature/home-screen-basic-login):
This is a placeholder identity step (no password, no DB) - see
login_prompt.py's own docstring for why ClientCore only ever calls
LoginPrompt.get_username() and never knows a terminal is involved.
prepare_login() only collects the username locally; connect() is what
actually sends it (as a LoginRequest) and blocks until the server's
welcome arrives - role assignment now follows login order, not raw
connection order (see session.py/ws_server.py).

Coordinates are (row, col), matching the internal model exactly (see
model/position.py): row 0 is the BLACK back rank (top), row 7 is the
WHITE back rank (bottom) - the same convention BoardParser/BoardPrinter
already use elsewhere in this project. Piece tokens (e.g. "wK", "bP")
match BoardPrinter's own format for the same reason: no new convention
to learn if you've already used `print board` in the CLI grader.

WHY stdin IS READ VIA run_in_executor(None, sys.stdin.readline) INSTEAD
OF SOME ASYNC-NATIVE INPUT LIBRARY, AND NOT VIA THE BUILTIN input():
Reading in a worker thread (rather than blocking the event loop) is
what lets ClientCore's background listen task keep dispatching incoming
broadcasts - so the board updates live even while waiting on the next
typed command - without pulling in an extra dependency (e.g.
aioconsole) for a manual-testing-only script. The first version of this
file used run_in_executor(None, input, "> "), which looked like the
obvious way to get that same thread-not-loop blocking; running it
against a real server (not just in-process tests) reproduced
`RuntimeError: input(): lost sys.stdin` - CPython's input() goes
through PyOS_Readline, which doesn't tolerate being called outside the
main thread. sys.stdin.readline() is a plain buffered read with no such
restriction, so the prompt is printed separately instead of relying on
input()'s built-in prompt argument.
"""

import asyncio
import sys

from kungfu_chess.model.position import Position
from kungfu_chess.network.client_core import ClientCore, SentRequest
from kungfu_chess.network.login_prompt import ShellLoginPrompt
from kungfu_chess.network.protocol import Error, GameStateUpdate
from kungfu_chess.network.ws_server import DEFAULT_HOST, DEFAULT_PORT


def _render(update: GameStateUpdate) -> str:
    grid = [["." for _ in range(update.board_width)] for _ in range(update.board_height)]
    for piece in update.pieces:
        grid[piece.row][piece.col] = f"{piece.color}{piece.kind}"
    board_text = "\n".join(" ".join(row) for row in grid)

    motion_lines = [
        f"  in flight: {m.source.row},{m.source.col} -> {m.destination.row},{m.destination.col}"
        for m in update.motions
    ]
    status = f"you are: {update.your_color or 'spectator'} | game_over={update.game_over}"
    if update.winner:
        status += f" | winner={update.winner}"
    return "\n".join([board_text, status, *motion_lines])


def _parse_position(token: str) -> Position:
    row_str, col_str = token.split(",")
    return Position(int(row_str), int(col_str))


def _should_reprint(previous, current: GameStateUpdate) -> bool:
    """The server broadcasts on a fixed ~20Hz tick regardless of whether
    anything changed (ws_server.py's own design choice - see its module
    docstring). Printing every single one would flood the terminal with
    dozens of identical board dumps per second even while nothing is
    happening - discovered by actually running this against a real
    server rather than assuming. GameStateUpdate is a plain dataclass, so
    equality already compares every field (pieces, motions, game_over,
    your_color, ...); an in-flight motion's (start_time_ms,
    arrival_time_ms) don't change tick to tick either; so this only
    lets a genuinely new state (a move started, arrived, or the game
    ended) through."""
    return current != previous


async def _read_command() -> str:
    print("> ", end="", flush=True)
    loop = asyncio.get_event_loop()
    line = await loop.run_in_executor(None, sys.stdin.readline)
    return line.rstrip("\n")


async def _run(uri: str) -> None:
    client = ClientCore(uri, login_prompt=ShellLoginPrompt())
    client.prepare_login()
    print(f"logging in as: {client.username}")

    last_printed: "GameStateUpdate | None" = None

    def _on_state_update(update: GameStateUpdate) -> None:
        nonlocal last_printed
        if _should_reprint(last_printed, update):
            last_printed = update
            print("\n" + _render(update))

    def _on_error(error: Error, request: "SentRequest | None") -> None:
        print(f"\n[error] reason={error.reason} request_id={error.request_id}")

    client.on_state_update(_on_state_update)
    client.on_error(_on_error)

    await client.connect()
    print(f"connected as: {client.my_color or 'spectator'}")
    print("commands: move <r>,<c> <r>,<c>  |  jump <r>,<c>  |  quit")

    try:
        while True:
            line = (await _read_command()).strip()
            if not line or line == "quit":
                break
            parts = line.split()
            try:
                if parts[0] == "move":
                    if len(parts) != 3:
                        print("usage: move <src_row>,<src_col> <dst_row>,<dst_col>  e.g. move 6,4 4,4")
                    else:
                        await client.send_move(_parse_position(parts[1]), _parse_position(parts[2]))
                elif parts[0] == "jump":
                    if len(parts) != 2:
                        print("usage: jump <row>,<col>  e.g. jump 6,4")
                    else:
                        await client.send_jump(_parse_position(parts[1]))
                else:
                    print(f"unrecognized command: {parts[0]!r} (try: move / jump / quit)")
            except ValueError:
                print("bad coordinates - expected e.g. '6,4'")
    finally:
        await client.close()


def main() -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    asyncio.run(_run(f"ws://{host}:{port}"))


if __name__ == "__main__":
    main()