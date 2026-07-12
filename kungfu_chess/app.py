"""
app.py: the composition root. Its only job is wiring - reading a starting
board, constructing one of each collaborator, and handing control to
whatever event loop the real drawing library provides. It must contain no
game logic itself (same rule main.py followed in the previous version of
this project).

This module intentionally stops short of an actual pygame/tkinter event
loop, since "the supplied drawing/image library" is an environment detail
outside this deliverable's scope (see view/renderer.py's docstring). What
matters architecturally is shown here: every real click would go through
`controller.click(x, y)`, every frame would read `engine.snapshot()` and
hand it to `renderer.draw(...)`, and nothing here ever reaches into
Board, RuleEngine or RealTimeArbiter directly.
"""

from kungfu_chess.io.board_parser import BoardParser
from kungfu_chess.io.board_printer import BoardPrinter
from kungfu_chess.input.board_mapper import BoardMapper
from kungfu_chess.input.controller import Controller
from kungfu_chess.engine.game_engine import GameEngine
from kungfu_chess.view.renderer import Renderer


def build_game(board_text_rows):
    parser = BoardParser()
    board = parser.parse(board_text_rows)

    engine = GameEngine(board)
    mapper = BoardMapper(board)
    controller = Controller(mapper, engine)
    renderer = Renderer()
    printer = BoardPrinter()

    return engine, controller, renderer, printer


if __name__ == "__main__":
    starting_position = [
        "bR bN bB bQ bK bB bN bR".split(),
        ["bP"] * 8,
        [".", ".", ".", ".", ".", ".", ".", "."],
        [".", ".", ".", ".", ".", ".", ".", "."],
        [".", ".", ".", ".", ".", ".", ".", "."],
        [".", ".", ".", ".", ".", ".", ".", "."],
        ["wP"] * 8,
        "wR wN wB wQ wK wB wN wR".split(),
    ]
    engine, controller, renderer, printer = build_game(starting_position)
    print(printer.print_board(engine.board))
