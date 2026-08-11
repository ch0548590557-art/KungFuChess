"""
MatchmakingQueue: waits for two players within rating_range of each
other to both call enqueue(), then publishes MatchFoundEvent for
whoever is listening (SessionManager, Step 2 of feature/matchmaking-
disconnect) - and gives up on a lone waiter after timeout_seconds with
MatchmakingTimeout.

WHY THIS KNOWS NOTHING ABOUT SessionManager/GameSession/NETWORKING:
Same reasoning as login_gate.py's own module docstring - "find two
ratings within range of each other and say so" has nothing chess-
specific or connection-specific about it. Keeping this ignorant of
everything downstream means Step 2 only has to wire *a* MatchFoundEvent
subscriber; this module doesn't change shape to accommodate it. The one
way this ever talks to anything else is MatchFoundEvent on the EventBus
it's constructed with (bus/events.py) - not a callback, not a direct
reference to SessionManager, matching how GameEngine already publishes
MoveCompletedEvent/GameEndedEvent without knowing who (if anyone) is
subscribed.

WHY FIRST MATCH (THE FIRST QUEUED ENTRY WITHIN RANGE) RATHER THAN BEST
MATCH (THE CLOSEST RATING IN RANGE):
Deliberate simplicity - scanning the queue in FIFO order and taking the
first candidate within rating_range is O(n) with no sorting/tie-breaking
logic to get right. Best-match would also mean a player's wait time
depends on who else happens to be in the queue in ways that are harder
to reason about (and to test) for a one-active-game system where the
queue is rarely more than a couple of entries deep anyway.

WHY WHO PLAYS WHITE IS DECIDED BY joined_at RATHER THAN BY WHICH SIDE OF
THE enqueue() CALL DID THE MATCHING:
The entry already waiting in the queue when a match happens has, by
construction, an earlier joined_at than the entry that just called
enqueue() and triggered the match - but comparing joined_at explicitly
(instead of just assuming "the one already in the queue") keeps the
color assignment correct even if this module's internals change later,
and gives _assign_colors() something meaningful to unit-test on its own.

WHY THE QUEUED SIDE'S enqueue() COROUTINE ISN'T THE ONE THAT PUBLISHES
MatchFoundEvent:
Only one MatchFoundEvent may be published per pair. The side that calls
enqueue() *while an opponent is already waiting* is the one running
synchronous code that finds the match, removes the opponent from the
queue, and decides colors - so it is the natural, single place to
publish from. The waiting side's enqueue() call is woken via a plain
per-entry asyncio.Event and simply returns; it never touches the bus.

WHY THE WAITING SIDE'S TIMEOUT MUST BE EXPLICITLY CANCELLED THE MOMENT A
MATCH IS FOUND, RATHER THAN LEFT TO ELAPSE HARMLESSLY:
A naive design of "schedule a timeout, ignore it after a match" risks
the timeout still firing later and reporting matchmaking_timeout to a
player who is, by then, already in a game - a stale, wrong message
sent behind whatever handles the *result* of a match. enqueue() uses
asyncio.wait() over an explicit {match_task, timeout_task} pair and
cancels whichever one didn't win, and additionally re-checks
entry.matched after a TimeoutError-shaped result before ever raising -
so even a match that lands in the same event-loop tick as the timeout
is honored over the timeout. test_matchmaking_queue.py asserts this
directly (a match arriving well inside the window, then waiting past
the original timeout, must never raise and must never publish a second
MatchFoundEvent) rather than only assuming asyncio.wait_for would have
handled it.

WHY cancel() IS IDEMPOTENT INSTEAD OF RAISING WHEN THE USERNAME ISN'T
QUEUED:
A CancelPlayRequest racing with a match being found (or with a timeout,
or simply never having been queued in the first place) is an ordinary,
expected race in a system with independent, concurrently-running
coroutines - not a client error. Raising here would force every caller
to wrap cancel() in a try/except for a condition that isn't exceptional.
There is no genuine race in practice: neither cancel() nor the matching
branch of enqueue() ever awaits before finishing its queue mutation, so
asyncio's cooperative scheduling means exactly one of "cancel removed it
first" / "a match removed it first" is always true - cancel() calling
into an already-matched entry simply finds nothing there and returns
False, the same as any other not-queued case.

WHY enqueue()'s finally BLOCK REMOVES THE ENTRY ON *ANY* UNMATCHED EXIT,
NOT JUST THE TIMEOUT BRANCH:
MatchmakingQueue has no idea what a "disconnect" is (see above) - the
only way it ever finds out a waiting player is gone is either an
explicit cancel(username) call, or its own enqueue() task getting
cancelled from outside (asyncio.CancelledError), e.g. a caller that
reacts to a dropped connection by cancelling the task directly instead
of calling cancel() first. A CancelledError unwinds straight through the
try block into finally without ever reaching a dedicated "remove from
queue" line - so removal has to live in finally, guarded only by
"wasn't already matched/cancelled", to guarantee no exit path (match,
timeout, cancel, or bare task cancellation) can ever leave a stale
"ghost" entry sitting in the queue.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import List, Optional

from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import MatchFoundEvent

DEFAULT_RATING_RANGE = 100
DEFAULT_QUEUE_TIMEOUT_SECONDS = 60.0


class MatchmakingTimeout(Exception):
    """Raised from enqueue() when no opponent within rating_range showed
    up before timeout_seconds elapsed - the caller (Step 2) is expected
    to catch this and report Error(reason="matchmaking_timeout")."""

    def __init__(self, username: str):
        super().__init__(f"matchmaking timeout: {username}")
        self.username = username


@dataclass
class _QueueEntry:
    username: str
    rating: int
    joined_at: float
    # Set for both "matched" and "cancelled" - enqueue() only needs to know
    # "stop waiting", not which; see cancel()'s and enqueue()'s docstrings.
    matched: asyncio.Event = field(default_factory=asyncio.Event)


class MatchmakingQueue:
    def __init__(
        self,
        bus: EventBus,
        rating_range: int = DEFAULT_RATING_RANGE,
        timeout_seconds: float = DEFAULT_QUEUE_TIMEOUT_SECONDS,
    ):
        self._bus = bus
        self._rating_range = rating_range
        self._timeout_seconds = timeout_seconds
        self._queue: List[_QueueEntry] = []

    async def enqueue(self, username: str, rating: int) -> None:
        """Blocks until either a same-range opponent is found (returns
        normally - MatchFoundEvent has already been published by then),
        the wait is cancelled via cancel() (returns normally, no event),
        or timeout_seconds elapses with no opponent (raises
        MatchmakingTimeout). If the awaiting task itself is cancelled from
        outside (asyncio.CancelledError - e.g. a caller reacting to a
        dropped connection by cancelling the task instead of calling
        cancel()), the entry is still removed before the CancelledError
        propagates - see the module docstring's queue-cleanup note."""
        opponent = self._find_opponent(rating, exclude_username=username)
        if opponent is not None:
            self._queue.remove(opponent)
            entry = _QueueEntry(username=username, rating=rating, joined_at=time.monotonic())
            self._match(opponent, entry)
            return

        entry = _QueueEntry(username=username, rating=rating, joined_at=time.monotonic())
        self._queue.append(entry)

        match_task = asyncio.ensure_future(entry.matched.wait())
        timeout_task = asyncio.ensure_future(asyncio.sleep(self._timeout_seconds))
        try:
            await asyncio.wait({match_task, timeout_task}, return_when=asyncio.FIRST_COMPLETED)

            # A match found in the same tick the timeout fired must still
            # win - see the module docstring's explicit-cancellation note.
            if entry.matched.is_set():
                return

            raise MatchmakingTimeout(username)
        finally:
            match_task.cancel()
            timeout_task.cancel()
            # Every exit path lands here - normal timeout, the early return
            # above, or this coroutine's own task being cancelled from
            # outside (asyncio.CancelledError unwinds through this finally
            # too). entry.matched being set means match()/cancel() already
            # removed it themselves; anything else (timeout, or an outside
            # cancellation while still genuinely waiting) must remove it
            # here, or a stale "ghost" entry is left in the queue forever.
            if not entry.matched.is_set() and entry in self._queue:
                self._queue.remove(entry)

    def cancel(self, username: str) -> bool:
        """Removes username from the queue if present and wakes its
        waiting enqueue() call (which returns normally, no exception, no
        event). Idempotent: returns False, does not raise, if username
        isn't queued (never was, already matched, or already timed out)."""
        for entry in self._queue:
            if entry.username == username:
                self._queue.remove(entry)
                entry.matched.set()
                return True
        return False

    def _find_opponent(self, rating: int, exclude_username: str) -> Optional[_QueueEntry]:
        for entry in self._queue:
            if entry.username == exclude_username:
                continue
            if abs(entry.rating - rating) <= self._rating_range:
                return entry
        return None

    def _match(self, entry_a: _QueueEntry, entry_b: _QueueEntry) -> None:
        white, black = _assign_colors(entry_a, entry_b)
        white.matched.set()
        black.matched.set()
        self._bus.publish(MatchFoundEvent(white_username=white.username, black_username=black.username))


def _assign_colors(entry_a: _QueueEntry, entry_b: _QueueEntry):
    """Whoever has been waiting longer (the smaller joined_at) plays
    White - see the module docstring."""
    if entry_a.joined_at <= entry_b.joined_at:
        return entry_a, entry_b
    return entry_b, entry_a