"""
repl_client: a minimal interactive terminal client for manually
playtesting the WS transport end-to-end (Step 5). Connects via
ClientCore, prints the board as text after every update, and reads
"move <r>,<c> <r>,<c>" / "jump <r>,<c>" / "quit" from stdin.

Not a real game client - no login, no graphics, no algebraic notation.
It exists purely so a human can drive two independent terminal
processes against the same WebSocketServer and watch a real game play
out, proving the whole stack (protocol -> SessionManager -> GameSession
-> GameEngine -> RealTimeArbiter's tick-driven arrivals) works end to
end. A real UI is later work, on top of this same ClientCore.

Coordinates are (row, col), matching the internal model exactly (see
model/position.py): row 0 is the BLACK back rank (top), row 7 is the
WHITE back rank (bottom) - the same convention BoardParser/BoardPrinter
already use elsewhere in this project. Piece tokens (e.g. "wK", "bP")
match BoardPrinter's own format for the same reason: no new convention
to learn if you've already used `print board` in the CLI grader.

WHY stdin IS READ VIA run_in_executor(None, input) INSTEAD OF SOME
ASYNC-NATIVE INPUT LIBRARY:
input() blocks a thread, not the event loop, when run through
run_in_executor - that's enough to let ClientCore's background listen
task keep dispatching incoming broadcasts (so the board updates live,
even while waiting on the next typed command) without pulling in an
extra dependency (e.g. aioconsole) for a manual-testing-only script.
"""

import asyncio
import sys

from kungfu_chess.model.position import Position
from kungfu_chess.network.client_core import ClientCore, SentRequest
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


async def _read_command() -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input, "> ")


async def _run(uri: str) -> None:
    client = ClientCore(uri)

    def _on_state_update(update: GameStateUpdate) -> None:
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
                if parts[0] == "move" and len(parts) == 3:
                    await client.send_move(_parse_position(parts[1]), _parse_position(parts[2]))
                elif parts[0] == "jump" and len(parts) == 2:
                    await client.send_jump(_parse_position(parts[1]))
                else:
                    print("unrecognized command")
            except (IndexError, ValueError):
                print("bad coordinates - expected e.g. 'move 6,4 4,4'")
    finally:
        await client.close()


def main() -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    asyncio.run(_run(f"ws://{host}:{port}"))


if __name__ == "__main__":
    main()