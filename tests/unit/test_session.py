from kungfu_chess.network.session import PlayerRole, SessionManager


def test_first_connection_gets_white():
    manager = SessionManager()
    session = manager.register_connection("conn-1")
    assert session.role is PlayerRole.WHITE
    assert session.color == "w"


def test_second_connection_gets_black():
    manager = SessionManager()
    manager.register_connection("conn-1")
    second = manager.register_connection("conn-2")
    assert second.role is PlayerRole.BLACK
    assert second.color == "b"


def test_third_and_later_connections_become_spectators():
    manager = SessionManager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    third = manager.register_connection("conn-3")
    fourth = manager.register_connection("conn-4")

    assert third.role is PlayerRole.SPECTATOR
    assert third.color is None
    assert fourth.role is PlayerRole.SPECTATOR
    assert fourth.color is None


def test_unregister_frees_color_for_the_next_new_connection():
    manager = SessionManager()
    manager.register_connection("conn-1")          # white
    manager.register_connection("conn-2")           # black

    manager.unregister_connection("conn-1")

    replacement = manager.register_connection("conn-3")
    assert replacement.role is PlayerRole.WHITE


def test_unregister_does_not_promote_an_existing_spectator():
    manager = SessionManager()
    manager.register_connection("conn-1")            # white
    manager.register_connection("conn-2")            # black
    spectator = manager.register_connection("conn-3")  # spectator
    assert spectator.role is PlayerRole.SPECTATOR

    manager.unregister_connection("conn-1")           # white leaves

    # The already-connected spectator's role is untouched by the
    # departure - only a *new* register_connection() call can claim
    # the freed color (see module docstring: no auto-promotion).
    assert spectator.role is PlayerRole.SPECTATOR


def test_unregister_unknown_connection_is_a_no_op():
    manager = SessionManager()
    manager.unregister_connection("never-registered")  # must not raise