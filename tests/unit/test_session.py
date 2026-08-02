from kungfu_chess.network.session import PlayerRole, SessionManager


def test_register_connection_creates_a_pending_session_with_no_role():
    manager = SessionManager()
    session = manager.register_connection("conn-1")

    assert session.role is None
    assert session.color is None
    assert session.is_logged_in is False


def test_first_login_gets_white():
    manager = SessionManager()
    manager.register_connection("conn-1")

    session = manager.complete_login("conn-1", "alice")

    assert session.role is PlayerRole.WHITE
    assert session.color == "w"
    assert session.username == "alice"
    assert session.is_logged_in is True


def test_second_login_gets_black():
    manager = SessionManager()
    manager.register_connection("conn-1")
    manager.register_connection("conn-2")
    manager.complete_login("conn-1", "alice")

    session = manager.complete_login("conn-2", "bob")

    assert session.role is PlayerRole.BLACK
    assert session.color == "b"


def test_third_and_later_logins_become_spectators():
    manager = SessionManager()
    for conn in ("conn-1", "conn-2", "conn-3", "conn-4"):
        manager.register_connection(conn)
    manager.complete_login("conn-1", "alice")
    manager.complete_login("conn-2", "bob")

    third = manager.complete_login("conn-3", "carol")
    fourth = manager.complete_login("conn-4", "dave")

    assert third.role is PlayerRole.SPECTATOR
    assert third.color is None
    assert fourth.role is PlayerRole.SPECTATOR
    assert fourth.color is None


def test_role_is_assigned_by_login_order_not_connection_order():
    """The exact scenario this split exists for: connection order and
    login-completion order can differ, and role assignment must follow
    the latter."""
    manager = SessionManager()
    manager.register_connection("conn-first-to-connect")
    manager.register_connection("conn-second-to-connect")

    # The second connection logs in first.
    first_login = manager.complete_login("conn-second-to-connect", "bob")
    second_login = manager.complete_login("conn-first-to-connect", "alice")

    assert first_login.role is PlayerRole.WHITE
    assert second_login.role is PlayerRole.BLACK


def test_unregister_frees_color_for_the_next_new_login():
    manager = SessionManager()
    manager.register_connection("conn-1")
    manager.complete_login("conn-1", "alice")   # white
    manager.register_connection("conn-2")
    manager.complete_login("conn-2", "bob")     # black

    manager.unregister_connection("conn-1")

    manager.register_connection("conn-3")
    replacement = manager.complete_login("conn-3", "carol")
    assert replacement.role is PlayerRole.WHITE


def test_unregister_does_not_promote_an_existing_spectator():
    manager = SessionManager()
    for conn in ("conn-1", "conn-2", "conn-3"):
        manager.register_connection(conn)
    manager.complete_login("conn-1", "alice")            # white
    manager.complete_login("conn-2", "bob")               # black
    spectator = manager.complete_login("conn-3", "carol")  # spectator
    assert spectator.role is PlayerRole.SPECTATOR

    manager.unregister_connection("conn-1")  # white leaves

    # The already-connected spectator's role is untouched by the
    # departure - only a *new* login can claim the freed color (see
    # module docstring: no auto-promotion).
    assert spectator.role is PlayerRole.SPECTATOR


def test_unregister_a_connection_that_never_logged_in_is_a_no_op():
    manager = SessionManager()
    manager.register_connection("conn-1")

    manager.unregister_connection("conn-1")  # must not raise, must not touch role_taken

    manager.register_connection("conn-2")
    replacement = manager.complete_login("conn-2", "alice")
    assert replacement.role is PlayerRole.WHITE  # nothing was ever taken


def test_unregister_unknown_connection_is_a_no_op():
    manager = SessionManager()
    manager.unregister_connection("never-registered")  # must not raise