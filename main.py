"""
main.py: the CLI adapter for the course's automated grader.
"""

import sys

from kungfu_chess.io.board_parser import BoardParser, BoardParseError
from kungfu_chess.io.board_printer import BoardPrinter
from kungfu_chess.input.board_mapper import BoardMapper
from kungfu_chess.input.controller import Controller
from kungfu_chess.engine.game_engine import GameEngine


def _split_sections(text: str):
    rows, command_lines = [], []
    mode = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "Board:":
            mode = "board"
            continue
        if line == "Commands:":
            mode = "commands"
            continue
        if not line:
            continue
        if mode == "board":
            rows.append(line.split())
        elif mode == "commands":
            command_lines.append(line)

    return rows, command_lines


def run(text: str, out=sys.stdout) -> None:
    rows, command_lines = _split_sections(text)

    try:
        board = BoardParser().parse(rows)
    except BoardParseError as err:
        print(f"ERROR {err.reason.upper()}", file=out)
        return

    engine = GameEngine(board)
    controller = Controller(BoardMapper(board), engine)
    printer = BoardPrinter()

    for line in command_lines:
        if line.startswith("click "):
            _, x, y = line.split()
            controller.click(int(x), int(y))
        elif line.startswith("wait "):
            _, ms = line.split()
            engine.wait(int(ms))
        elif line == "print board":
            print(printer.print_board(engine.board), file=out)


if __name__ == "__main__":
    run(sys.stdin.read())