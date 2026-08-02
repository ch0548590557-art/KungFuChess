from kungfu_chess.model.position import Position
from kungfu_chess.network.protocol import GameStateUpdate, MotionInfo, PieceInfo
from kungfu_chess.network.repl_client import _parse_position, _render, _should_reprint


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


def test_render_shows_both_players_usernames():
    update = GameStateUpdate(
        board_width=1, board_height=1, pieces=[], game_over=False,
        white_username="alice", black_username="bob",
    )
    assert "white: alice | black: bob" in _render(update)


def test_render_shows_placeholder_for_a_username_not_logged_in_yet():
    update = GameStateUpdate(
        board_width=1, board_height=1, pieces=[], game_over=False,
        white_username="alice", black_username=None,
    )
    assert "white: alice | black: ?" in _render(update)


def test_should_not_reprint_an_identical_tick_broadcast():
    """The server broadcasts ~20 times/second regardless of whether
    anything changed - discovered as a real terminal-flooding bug when
    actually running this against a live server (dozens of identical
    board dumps per second while nothing was happening)."""
    update = GameStateUpdate(board_width=1, board_height=1, pieces=[], game_over=False)
    assert _should_reprint(None, update) is True  # first update always prints
    assert _should_reprint(update, update) is False


def test_should_reprint_when_the_state_actually_changes():
    before = GameStateUpdate(board_width=1, board_height=1, pieces=[], game_over=False)
    after = GameStateUpdate(board_width=1, board_height=1, pieces=[], game_over=True, winner="w")
    assert _should_reprint(before, after) is True