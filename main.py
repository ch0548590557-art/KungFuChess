

import sys

from engine import GameEngine
from input_parser import parse_lines, InputError


def main():
    try:
        board_rows, commands = parse_lines(sys.stdin)
    except InputError as e:
        print(e.message)
        return

    if board_rows is None:
        return

    engine = GameEngine(board_rows)

    for cmd in commands:
        engine.handle_command(cmd)


if __name__ == "__main__":
    main()
