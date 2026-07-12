from kungfu_chess.io.board_parser import BoardParser
from kungfu_chess.io.board_printer import BoardPrinter


def test_board_round_trips_through_parser_and_printer():
    rows = [["wK", ".", "."], [".", "wR", "bK"]]
    board = BoardParser().parse(rows)
    text = BoardPrinter().print_board(board)
    assert text == "wK . .\n. wR bK"
