from kungfu_chess.model.position import Position
from kungfu_chess.network.protocol import GameStateUpdate, MotionInfo, PieceInfo
from kungfu_chess.network.repl_client import _parse_position, _render


def test_parse_position():
    assert _parse_position("6,4") == Position(6, 4)


def test_render_places_pieces_using_board_printer_style_tokens():
    update = GameStateUpdate(
        board_width=3, board_height=2,
        pieces=[PieceInfo(kind="K", color="w", row=0, col=1, state="IDLE")],
        game_over=False, your_color="w",
    )
    text = _render(update)
    assert ". wK ." in text
    assert "you are: w" in text


def test_render_shows_in_flight_motions():
    update = GameStateUpdate(
        board_width=2, board_height=2, pieces=[], game_over=False,
        motions=[MotionInfo(
            source=Position(0, 0), destination=Position(1, 1),
            start_time_ms=0, arrival_time_ms=1000,
        )],
    )
    assert "in flight: 0,0 -> 1,1" in _render(update)


def test_render_shows_spectator_status():
    update = GameStateUpdate(
        board_width=1, board_height=1, pieces=[], game_over=False, your_color=None,
    )
    assert "you are: spectator" in _render(update)


def test_render_shows_winner_when_game_is_over():
    update = GameStateUpdate(
        board_width=1, board_height=1, pieces=[], game_over=True, winner="w",
    )
    text = _render(update)
    assert "game_over=True" in text
    assert "winner=w" in text