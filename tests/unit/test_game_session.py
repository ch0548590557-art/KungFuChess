from kungfu_chess.model.position import Position
from kungfu_chess.network import protocol
from kungfu_chess.network.game_session import GameSession


def test_legal_move_from_correct_color_is_accepted():
    game = GameSession()
    white = game.connect("conn-white")

    reply = game.handle_message(white, protocol.encode(
        protocol.MoveRequest(source=Position(6, 4), destination=Position(4, 4))
    ))

    assert reply is None


def test_illegal_move_returns_engines_own_reason():
    game = GameSession()
    white = game.connect("conn-white")

    # A rook has no legal diagonal hop from its own starting cell.
    reply = game.handle_message(white, protocol.encode(
        protocol.MoveRequest(source=Position(7, 0), destination=Position(5, 2))
    ))

    assert reply == protocol.Error(reason="illegal_piece_move")


def test_move_on_a_piece_of_the_wrong_color_is_rejected_before_reaching_the_engine():
    game = GameSession()
    white = game.connect("conn-white")
    game.connect("conn-black")

    # (1, 4) is a black pawn; the sender is White.
    reply = game.handle_message(white, protocol.encode(
        protocol.MoveRequest(source=Position(1, 4), destination=Position(3, 4))
    ))

    assert reply == protocol.Error(reason="wrong_color")


def test_spectator_move_is_rejected_without_reaching_the_engine():
    game = GameSession()
    game.connect("conn-white")
    game.connect("conn-black")
    spectator = game.connect("conn-spectator")

    reply = game.handle_message(spectator, protocol.encode(
        protocol.MoveRequest(source=Position(6, 4), destination=Position(4, 4))
    ))

    assert reply == protocol.Error(reason="spectators_cannot_move")


def test_spectator_jump_is_also_rejected():
    game = GameSession()
    game.connect("conn-white")
    game.connect("conn-black")
    spectator = game.connect("conn-spectator")

    reply = game.handle_message(spectator, protocol.encode(
        protocol.JumpRequest(source=Position(6, 4))
    ))

    assert reply == protocol.Error(reason="spectators_cannot_move")


def test_malformed_json_returns_malformed_message():
    game = GameSession()
    white = game.connect("conn-white")

    reply = game.handle_message(white, "not json at all")

    assert reply == protocol.Error(reason="malformed_message")


def test_unrecognized_type_returns_unknown_message_type():
    game = GameSession()
    white = game.connect("conn-white")

    reply = game.handle_message(white, '{"type": "not_a_real_type"}')

    assert reply == protocol.Error(reason="unknown_message_type")


def test_server_to_client_message_type_sent_by_a_client_is_rejected():
    game = GameSession()
    white = game.connect("conn-white")

    reply = game.handle_message(white, protocol.encode(protocol.Error(reason="whatever")))

    assert reply == protocol.Error(reason="unknown_message_type")


def test_accepted_move_triggers_the_move_completed_callback():
    game = GameSession()
    calls = []
    game.on_move_completed(lambda: calls.append(1))
    white = game.connect("conn-white")

    game.handle_message(white, protocol.encode(
        protocol.MoveRequest(source=Position(6, 4), destination=Position(4, 4))
    ))

    assert calls == [1]


def test_rejected_move_does_not_trigger_the_move_completed_callback():
    game = GameSession()
    calls = []
    game.on_move_completed(lambda: calls.append(1))
    white = game.connect("conn-white")
    game.connect("conn-black")

    game.handle_message(white, protocol.encode(
        protocol.MoveRequest(source=Position(1, 4), destination=Position(3, 4))
    ))

    assert calls == []


def test_tick_advances_the_engine_and_a_completed_motion_lands():
    game = GameSession()
    white = game.connect("conn-white")
    game.handle_message(white, protocol.encode(
        protocol.MoveRequest(source=Position(6, 4), destination=Position(4, 4))
    ))

    still_in_flight = game.state_update_for(white)
    assert len(still_in_flight.motions) == 1

    game.tick(5000)  # comfortably longer than a 2-cell pawn advance

    landed = game.state_update_for(white)
    assert landed.motions == []
    assert any(p.row == 4 and p.col == 4 and p.kind == "P" for p in landed.pieces)


def test_state_update_for_carries_the_recipients_own_color():
    game = GameSession()
    white = game.connect("conn-white")
    black = game.connect("conn-black")
    spectator = game.connect("conn-spectator")

    assert game.state_update_for(white).your_color == "w"
    assert game.state_update_for(black).your_color == "b"
    assert game.state_update_for(spectator).your_color is None