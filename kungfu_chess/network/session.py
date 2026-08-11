"""
session.py: tracks connections and assigns each one a role
(WHITE/BLACK/SPECTATOR), plus (as of feature/home-screen-basic-login) a
username. SessionManager does not know GameEngine, RuleEngine, or any
move legality - only "who is this connection and what role do they
have" in the narrowest sense. Connecting a Session's role to actual game
state (does GameEngine agree a move from this color is legal right now)
is game_session.py's job.

WHY register_connection() AND complete_login() ARE TWO SEPARATE STEPS
(split in feature/home-screen-basic-login, Step 3):
A raw WebSocket connection and an *identified* one are no longer the
same moment - a client now sends a LoginRequest(username) before it is
allowed to do anything else (see login_gate.py). register_connection()
therefore creates a role-less (pending) Session the instant a socket
connects; complete_login() is the only thing that ever turns it into a
*logged-in* Session (see is_logged_in below), called once a LoginRequest
actually arrives.

WHY complete_login() NO LONGER ASSIGNS A ROLE AT ALL (feature/
matchmaking-disconnect, Step 2):
Role assignment used to follow login order directly - whoever logged in
first got WHITE, second got BLACK, everyone else SPECTATOR. That
conflated two genuinely different facts: "this connection is
authenticated and has a username" and "this connection is one of the
two active players." Now a role only ever comes from an explicit match
(see _handle_match_found below) - complete_login() only ever produces
one of two outcomes: SPECTATOR, if a game is already fully staffed (both
WHITE and BLACK taken - decision 6: a newcomer while a game is running
can only ever watch, never silently join), or no role at all (None) if
it isn't - connected, identified, waiting for a reason to get one
(sending a PlayRequest, handled entirely outside this class - see
ws_server.py). Every *other* login is out of scope for this decision
until decided otherwise: nothing here auto-enters anyone into
matchmaking.

WHY Session.is_logged_in NOW MEANS "HAS A USERNAME" INSTEAD OF "HAS A
ROLE" (feature/matchmaking-disconnect, Step 2):
Before this branch, those were the same event (complete_login() set
both together), so testing one was indistinguishable from testing the
other. Now a fully logged-in connection routinely has role=None (no
active game, hasn't asked to play yet) - is_logged_in must answer "did
this connection ever complete login", not "does it currently have a
seat at the board", or every caller checking "is this a real,
identified connection" would get the wrong answer for the single most
common post-login state.

WHY complete_login() RAISES UsernameAlreadyLoggedInError INSTEAD OF
REPLACING THE EXISTING SESSION (decision 9, Step 2):
A second LoginRequest for a username that already has a live connection
is not "that player reconnecting" - reconnect/disconnect handling
doesn't exist yet (Step 3+ of this same branch), so there is no way yet
to tell "the old connection is dead, this is a legitimate reconnect"
apart from "someone else is trying to use this name while the first
connection is still live." Silently stealing the session out from under
the first connection would let a live connection lose its game to a
better-timed impostor with the same login; rejecting the *new* one is
the only safe default until reconnect exists to make the distinction.

WHY THIS CLASS SUBSCRIBES TO MatchFoundEvent DIRECTLY, INSTEAD OF
SOMETHING ELSE TRANSLATING IT INTO assign_role() CALLS:
MatchmakingQueue publishes MatchFoundEvent with the two matched
usernames and their colors already decided (whoever waited longer is
White - see matchmaking_queue.py) - there is nothing left to decide,
only "look up the two Sessions and give them their roles", which is
exactly the "who is this connection and what role do they have"
question this class already owns. Subscribing here means the one class
responsible for roles is the one place a role ever actually changes,
rather than splitting "decide the role" and "apply the role" across two
classes for no reason.

WHY begin_queueing()/end_queueing() AND THE "ALREADY QUEUED/ALREADY
PLAYING/GAME IN PROGRESS" CHECKS LIVE HERE, NOT IN MatchmakingQueue
(Step 2):
MatchmakingQueue (Step 1) was built deliberately ignorant of
SessionManager/GameSession/game state - it only ever answers "are these
two ratings close enough" and "has this wait gone on too long". Whether
a given PlayRequest is even allowed to reach MatchmakingQueue.enqueue()
at all is a *session* question (does this connection already have a
role, is it already queued, is a game already fully staffed) that only
this class can answer - so the guard has to live on this side of the
boundary, checked *before* ever calling enqueue(), rather than teaching
MatchmakingQueue anything new. See ws_server.py's PlayRequest handling
for the caller side of this.

WHY A SPECTATOR'S PlayRequest IS REJECTED WITH "game_in_progress"
RATHER THAN BEING ALLOWED TO QUEUE FOR WHENEVER THE CURRENT GAME ENDS
(Step 2, explicit decision after review):
Letting spectators queue while a game is still running would need a
fourth state beyond "no role" / "queued" / "playing" - "matched, waiting
for a slot to open" - plus a second, FIFO-of-*pairs* queue distinct from
MatchmakingQueue's queue-of-*individuals*, plus answers for what a
disconnect or CancelPlayRequest means in that state. That is real Room/
multi-game sequencing, explicitly scoped to a future layer (Rooms) this
branch does not build. Rejecting outright is the honest reflection of
what this layer actually supports today (exactly one active game, no
queueing for a next one) - it costs a spectator having to retry
PlayRequest once the current game ends, which nothing today can even
detect yet (Step 3+ handles that), rather than a queue entry silently
promising a "next game" this layer cannot deliver.

WHY unregister_connection() DOES NOT REMOVE AN ACTIVE PLAYER'S SESSION
ANYMORE, ONLY MARKS IT DISCONNECTED (feature/matchmaking-disconnect,
Step 3):
Before disconnect handling existed, every disconnect looked the same -
pop the Session, free the color if it held one. That's still correct for
a spectator or a role-less connection (nothing to preserve - see below),
but wrong for an active WHITE/BLACK player: the whole point of a
disconnect countdown is that the player's *seat* - role, color, username,
and everything a GameStateUpdate reports about them - stays exactly as
it was while they have a chance to reconnect (Step 5). Popping the
Session immediately would make them vanish from white_username/
black_username on the very next broadcast, indistinguishable from
having resigned. So an active player's Session stays in self._sessions,
under its now-dead connection key, with state flipped to DISCONNECTED -
_role_taken is *not* freed either, since the color isn't actually up for
grabs yet (auto-resign, Step 4, is what will eventually free it).

WHY unregister_connection() RETURNS Optional[Session] NOW, AND WHY THAT
RETURN VALUE DOUBLES AS GUARD 7B (feature/matchmaking-disconnect, Step
3):
ws_server.py needs to know exactly once per genuine disconnect whether
to start a disconnect-timer task for this session - starting a second
one for a session that's already DISCONNECTED (a flaky connection that
drops twice, or any other double-close) would leak a duplicate timer
racing the first. Rather than expose a separate "is a timer already
running" query the caller must remember to check before calling this,
unregister_connection() itself only returns a non-None Session the
*first* time an active player's connection closes (the transition
ACTIVE -> DISCONNECTED) - a second call for the same already-
DISCONNECTED session returns None, so the guard is enforced at the one
place state actually changes, not duplicated in the caller.

WHY A DISCONNECT TIMER IS SAFE WITH A PLAIN STATE CHECK, NO LOCK
(feature/matchmaking-disconnect, Step 3, decision 7c) - VERIFIED, NOT
ASSUMED:
This whole module, GameSession, WebSocketServer, and MatchmakingQueue
all run as coroutines/tasks on the *one* asyncio event loop
WebSocketServer.start()/_run_forever() creates (or a test's own
asyncio.run(scenario())) - there is no threading.Thread,
ProcessPoolExecutor, or run_in_executor() anywhere in this server-side
code path (grepped before writing this: the only threading in the whole
project is login_prompt.py's getpass fallback and repl_client.py's stdin
reader, both client-side CLI tooling that never touches SessionManager/
GameSession/WebSocketServer). Python's cooperative single-threaded
scheduling means unregister_connection() and a disconnect-timer task
checking session.state can never actually run *simultaneously* - one
completes fully before the other's next await point resumes - so a
plain `if session.state is SessionState.DISCONNECTED` is race-free
without a Lock, the same reasoning MatchmakingQueue's own queue
mutations already lean on (Step 1).

WHY THE DISCONNECT TIMER WAITS ON A PER-SESSION asyncio.Event RATHER
THAN JUST asyncio.sleep()ING (feature/matchmaking-disconnect, Step 3):
Deliberately mirrors login_gate.py's await_login() shape -
asyncio.wait_for(<awaitable that resolves early on success>, timeout=N)
- reused directly, not reinvented (see disconnect_timer.py). Nothing
sets session.reconnected in this step (reconnect handling is Step 5),
so in practice every disconnect timer built today always resolves via
the timeout branch - but building it as a wait_for-over-an-Event now,
instead of a bare asyncio.sleep(), means Step 5 only has to call
session.reconnected.set() to make an early return "just work", without
this code changing shape again.

WHY remaining_disconnect_seconds() IS COMPUTED FROM disconnected_at ON
EVERY CALL, WITH NO SCHEDULED BROADCAST OF ITS OWN (decision 8):
The existing ~20Hz tick loop (ws_server.py, Section 1) already
broadcasts a GameStateUpdate every tick regardless of what changed -
asking this method for the current countdown value each time that
broadcast is built is the smallest possible addition, and it can never
drift out of sync with real elapsed time the way a separately-scheduled
countdown-only timer could (e.g. under event-loop scheduling jitter).

WHY reconnect_candidate()/reconnect() ARE TWO SEPARATE METHODS INSTEAD OF
ONE reconnect_or_login() DOING EVERYTHING (feature/matchmaking-disconnect,
Step 5):
Whether a reconnect is even *allowed* right now depends on a fact this
class deliberately doesn't know - has the game already ended - see the
module docstring's opening line ("SessionManager does not know
GameEngine"). Splitting the read (reconnect_candidate: "is there a seat
to come back to") from the write (reconnect: "attach this connection to
it") is what lets GameSession.login() ask the question, consult
GameEngine.game_over itself, and only then decide whether to call the
mutator - the same read-then-decide-then-mutate shape begin_queueing()/
MatchmakingQueue.enqueue() already uses for the same reason (Step 2).

WHY unregister_connection() NOW CLEARS reconnected ON EVERY FRESH
DISCONNECT (Step 5):
reconnected is an asyncio.Event, which only ever moves one direction on
its own (unset -> set, via .set()) - reconnect() sets it once to wake a
pending disconnect-timer task. A player who reconnects and *then*
disconnects again would otherwise hand the second disconnect-timer task
an Event that's already permanently set, so
await_reconnect_or_timeout()'s asyncio.wait_for(reconnected.wait(), ...)
would return immediately instead of actually waiting out the timeout -
silently skipping the whole countdown (and therefore auto-resign) on
every disconnect after the first reconnect. Clearing it here, at the one
place a fresh countdown is about to start, is a no-op on an ordinary
first disconnect (the Event is already unset) and correct on every
later one.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, Optional, Set
import asyncio
import math
import time

from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import MatchFoundEvent
from kungfu_chess.network.disconnect_timer import DEFAULT_DISCONNECT_TIMEOUT_SECONDS


class PlayerRole(Enum):
    WHITE = auto()
    BLACK = auto()
    SPECTATOR = auto()


class SessionState(Enum):
    """A player's connectivity state - independent of PlayerRole (a
    spectator or role-less session is never anything but ACTIVE; only an
    active WHITE/BLACK player can become DISCONNECTED or RESIGNED).
    RESIGNED is produced by mark_resigned() (feature/matchmaking-
    disconnect, Step 4) the moment a disconnect timer actually expires
    without a reconnect - it was defined back in Step 3, before anything
    produced it, so Session.state's type didn't need to change shape
    again when Step 4 added the first producer."""
    ACTIVE = auto()
    DISCONNECTED = auto()
    RESIGNED = auto()


_ROLE_TO_COLOR = {PlayerRole.WHITE: "w", PlayerRole.BLACK: "b"}


class UsernameAlreadyLoggedInError(Exception):
    """Raised by complete_login() when `username` already belongs to a
    live (not-yet-disconnected) session - see the module docstring on why
    this rejects the new connection instead of replacing the old one."""

    def __init__(self, username: str):
        super().__init__(f"username already logged in: {username}")
        self.username = username
        self.reason = "already_logged_in"


@dataclass
class Session:
    connection: Any
    role: Optional[PlayerRole]  # None until a match assigns one (or complete_login() makes it SPECTATOR)
    connected_at: datetime
    username: Optional[str] = None
    state: SessionState = SessionState.ACTIVE
    disconnected_at: Optional[float] = None  # time.monotonic() at the moment state became DISCONNECTED
    # Set by a future reconnect (Step 5) to wake this session's pending
    # disconnect-timer task early - see the module docstring's note on
    # why the timer waits on this instead of a bare asyncio.sleep().
    reconnected: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def color(self) -> Optional[str]:
        """'w' / 'b' for an assigned player, None for a spectator, a
        role-less logged-in connection, OR a connection that hasn't
        logged in yet. Unaffected by state - a DISCONNECTED player keeps
        their color for as long as their Session exists (see
        unregister_connection())."""
        return _ROLE_TO_COLOR.get(self.role) if self.role is not None else None

    @property
    def is_logged_in(self) -> bool:
        """True from the moment complete_login() succeeds, regardless of
        role - see the module docstring on why this is no longer the same
        question as "does this session have a role"."""
        return self.username is not None


class SessionManager:
    def __init__(self, bus: EventBus, disconnect_timeout_seconds: float = DEFAULT_DISCONNECT_TIMEOUT_SECONDS):
        self._sessions: Dict[Any, Session] = {}
        self._role_taken = {PlayerRole.WHITE: False, PlayerRole.BLACK: False}
        self._queued_usernames: Set[str] = set()
        self._disconnect_timeout_seconds = disconnect_timeout_seconds
        bus.subscribe(MatchFoundEvent, self._handle_match_found)

    def register_connection(self, connection: Any) -> Session:
        """A socket just connected - no role yet, no username yet."""
        session = Session(connection=connection, role=None, connected_at=datetime.now(timezone.utc))
        self._sessions[connection] = session
        return session

    def complete_login(self, connection: Any, username: str) -> Session:
        """A LoginRequest just arrived for an already-registered
        connection. Assigns SPECTATOR if a game is already fully staffed,
        otherwise leaves role=None - see the module docstring on why this
        no longer assigns WHITE/BLACK. Raises UsernameAlreadyLoggedInError
        if `username` already belongs to another live session."""
        if any(s.username == username for s in self._sessions.values()):
            raise UsernameAlreadyLoggedInError(username)

        session = self._sessions[connection]
        session.username = username
        if self._role_taken[PlayerRole.WHITE] and self._role_taken[PlayerRole.BLACK]:
            session.role = PlayerRole.SPECTATOR
        return session

    def unregister_connection(self, connection: Any) -> Optional[Session]:
        """A connection's socket just closed. Spectators and role-less
        sessions vanish immediately - nothing about them needs to be
        preserved. An *active* WHITE/BLACK player is different: their
        Session stays (under this now-dead connection key), keeps its
        role/color/username, and is marked DISCONNECTED instead of being
        removed - see the module docstring.

        Returns the Session if - and only if - this call is the one that
        just transitioned it ACTIVE -> DISCONNECTED, so the caller
        (ws_server.py) knows to start exactly one disconnect-timer task
        for it. Returns None for a spectator/role-less disconnect (no
        timer applies) and for a *second* disconnect of an
        already-DISCONNECTED session (guard 7b - see the module
        docstring) - both are "nothing further to do" from the caller's
        perspective."""
        session = self._sessions.get(connection)
        if session is None:
            return None

        if session.role not in (PlayerRole.WHITE, PlayerRole.BLACK):
            self._sessions.pop(connection, None)
            if session.username is not None:
                self._queued_usernames.discard(session.username)
            return None

        if session.state is SessionState.DISCONNECTED:
            return None  # guard 7b: already disconnected - no second timer

        session.state = SessionState.DISCONNECTED
        session.disconnected_at = time.monotonic()
        # A *second* disconnect, after a successful Step 5 reconnect
        # already .set() this same Session's reconnected Event, must
        # start this new countdown with a fresh (unset) Event - otherwise
        # disconnect_timer.py's await_reconnect_or_timeout() would see it
        # already set and return immediately, skipping the wait entirely
        # and never giving this second disconnect a real countdown.
        session.reconnected.clear()
        return session

    def mark_resigned(self, session: Session) -> None:
        """Called by GameSession (feature/matchmaking-disconnect, Step 4)
        the moment a disconnect timer actually expires without a
        reconnect - the only producer of SessionState.RESIGNED (see its
        own docstring). Only flips state; role/color/username are left
        untouched for the same reason unregister_connection() leaves them
        - a resigned player's seat still needs to read correctly in
        white_username/black_username for the rest of the now-ended
        game. Safe to call even if `session` is already RESIGNED (the
        losing side of two near-simultaneous disconnect timeouts - see
        game_engine.py's resign() for the guard that makes that race
        harmless) - setting the same value twice is a no-op."""
        session.state = SessionState.RESIGNED

    def reconnect_candidate(self, username: str) -> Optional[Session]:
        """Returns the existing non-ACTIVE WHITE/BLACK Session for
        `username`, if one exists - a seat a fresh login for this
        username should be routed to GameSession.login()'s reconnect
        handling for (feature/matchmaking-disconnect, Step 5), rather
        than treated as a brand-new login. None covers every other case a
        caller needs to fall back to complete_login()'s ordinary path
        for: `username` was never seen before, or is currently ACTIVE
        elsewhere (complete_login()'s own duplicate-login guard, decision
        9, still applies).

        WHY THIS ALSO MATCHES RESIGNED, NOT JUST DISCONNECTED:
        A RESIGNED session's disconnect timer already expired, so there
        is no seat left to actually reattach to - but GameEngine.resign()
        (Step 4) always sets game_over=True as part of producing RESIGNED
        in the first place (see mark_resigned()'s only caller), so it is
        never possible for a RESIGNED session to exist while game_over is
        still False. Returning it here, instead of leaving it for
        complete_login() to reject as an ordinary "already logged in"
        duplicate, is what lets GameSession.login() give this the same
        accurate "the game already ended" rejection a DISCONNECTED seat
        whose game ended for some *other* reason gets (see login()'s own
        docstring) - not the misleading "someone else is using this
        name" a genuinely-ACTIVE duplicate gets."""
        session = self._session_for_username(username)
        if (session is not None and session.role in (PlayerRole.WHITE, PlayerRole.BLACK)
                and session.state is not SessionState.ACTIVE):
            return session
        return None

    def reconnect(self, new_connection: Any, session: Session) -> Session:
        """Reattaches `session` (a reconnect_candidate()) onto
        `new_connection` - the socket a fresh LoginRequest for the same
        username just arrived on. Discards the fresh, still role-less
        Session register_connection() already created for
        `new_connection` (see connect()/register_connection() - every
        socket gets one immediately, before login is known to be a
        reconnect or not) in favor of `session`, which keeps its
        role/color/username throughout. Sets session.reconnected (see
        disconnect_timer.py) so the pending disconnect-timer task waiting
        on it wakes up and returns normally instead of ever raising
        ReconnectTimeout - GameSession.login() (the only caller) is
        responsible for having already confirmed the game hasn't ended in
        the meantime before calling this (see its own docstring on why
        that check has to happen first, and why it's safe to trust once
        made)."""
        self._sessions.pop(session.connection, None)
        self._sessions.pop(new_connection, None)
        session.connection = new_connection
        session.state = SessionState.ACTIVE
        session.disconnected_at = None
        session.reconnected.set()
        self._sessions[new_connection] = session
        return session

    def username_for_role(self, role: PlayerRole) -> Optional[str]:
        """The username of whichever session currently holds `role`
        (WHITE or BLACK), or None if nobody has logged in as that color
        yet. Used so a GameStateUpdate broadcast can tell every client
        who they're playing against, not just their own color."""
        session = self._session_for_role(role)
        return session.username if session is not None else None

    def remaining_disconnect_seconds(self) -> Optional[int]:
        """None if no active WHITE/BLACK player is currently
        DISCONNECTED; otherwise the smallest whole number of seconds
        left before whichever disconnected player's timer expires -
        recomputed from real elapsed time on every call, never cached
        (decision 8 - see the module docstring). If both colors happen
        to be disconnected at once, the *sooner* deadline is reported -
        the more urgent of the two is the only one worth surfacing to
        clients watching a single countdown field."""
        remaining = None
        for role in (PlayerRole.WHITE, PlayerRole.BLACK):
            session = self._session_for_role(role)
            if session is None or session.state is not SessionState.DISCONNECTED:
                continue
            elapsed = time.monotonic() - session.disconnected_at
            this_remaining = max(0, math.ceil(self._disconnect_timeout_seconds - elapsed))
            remaining = this_remaining if remaining is None else min(remaining, this_remaining)
        return remaining

    def _session_for_role(self, role: PlayerRole) -> Optional[Session]:
        for session in self._sessions.values():
            if session.role is role:
                return session
        return None

    def begin_queueing(self, username: str) -> Optional[str]:
        """Called before forwarding a PlayRequest to MatchmakingQueue.
        Returns an Error reason ("already_playing" / "already_in_queue" /
        "game_in_progress") if `username` may not enter the queue right
        now, or None if it's fine - in which case `username` is marked
        queued so a second PlayRequest for it is rejected without ever
        reaching MatchmakingQueue.enqueue() (see the module docstring).

        WHY THIS ORDER SPECIFICALLY (checked most-specific-to-`username`
        first, most-general-fact-about-the-server last):
        already_playing and already_in_queue are both facts about this
        *specific* username's own state; game_in_progress is a fact about
        the server that happens to be true for anyone right now,
        regardless of who's asking. These aren't mutually exclusive - a
        username can be sitting in the queue (already_in_queue) at the
        exact moment some *other* pair matches each other and fills both
        colors (game_in_progress becomes true too), since MatchmakingQueue
        resolves independently of any one username's own wait. Checking
        game_in_progress before already_in_queue would report the
        generic, less informative reason for a username that in fact has
        a perfectly specific one - see
        test_begin_queueing_prefers_already_in_queue_over_game_in_progress_when_both_apply
        in test_session.py."""
        session = self._session_for_username(username)
        if session is not None and session.role in (PlayerRole.WHITE, PlayerRole.BLACK):
            return "already_playing"
        if username in self._queued_usernames:
            return "already_in_queue"
        if self._role_taken[PlayerRole.WHITE] and self._role_taken[PlayerRole.BLACK]:
            return "game_in_progress"
        self._queued_usernames.add(username)
        return None

    def end_queueing(self, username: str) -> None:
        """Called once MatchmakingQueue.enqueue() has resolved for
        `username` by any outcome (matched, timed out, or cancelled) -
        always clears the "currently queued" bookkeeping so a later
        PlayRequest is allowed again. Idempotent - a match already clears
        this itself (see _assign_role below), so calling it again here is
        a harmless no-op."""
        self._queued_usernames.discard(username)

    def _session_for_username(self, username: str) -> Optional[Session]:
        for session in self._sessions.values():
            if session.username == username:
                return session
        return None

    def _handle_match_found(self, event: MatchFoundEvent) -> None:
        white = self._session_for_username(event.white_username)
        black = self._session_for_username(event.black_username)
        # Both should always resolve: begin_queueing() only ever marks a
        # username queued while it still has a live Session. A session
        # could in theory vanish between being queued and being matched
        # if its connection dropped in between - disconnect handling
        # doesn't exist yet (Step 3+ of this branch) so that gap is real
        # but out of scope here; skip silently rather than crash, since
        # there is no connection left to hand a role to anyway.
        if white is not None:
            self._assign_role(white, PlayerRole.WHITE)
        if black is not None:
            self._assign_role(black, PlayerRole.BLACK)

    def _assign_role(self, session: Session, role: PlayerRole) -> None:
        session.role = role
        self._role_taken[role] = True
        self._queued_usernames.discard(session.username)