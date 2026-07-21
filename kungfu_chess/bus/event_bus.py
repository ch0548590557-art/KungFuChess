"""
EventBus: a minimal publish/subscribe channel. Components publish events
without knowing who (if anyone) is listening, and subscribe to event
types without knowing which component publishes them - this is the
decoupling point the message-bus migration plan uses to replace direct
GameWindow -> InputRouter -> Controller -> GameEngine -> Renderer wiring.

WHY subscribe() KEYS ON THE EVENT'S TYPE RATHER THAN A STRING NAME:
Event types already live in events.py as distinct dataclasses, so using
the class itself as the key means a typo in a string ("mouse_clik") can
never silently create a dead subscription - it would be a NameError at
import time instead.

WHAT THIS DELIBERATELY DOES NOT DO:
No priorities, no unsubscribe, no async delivery, no error isolation
between handlers. The migration plan only needs synchronous, in-process
fan-out; adding any of that now would be solving a problem this refactor
doesn't have yet.
"""

from collections import defaultdict
from typing import Callable, DefaultDict, List, Type, TypeVar

EventT = TypeVar("EventT")


class EventBus:
    def __init__(self):
        self._subscribers: DefaultDict[Type, List[Callable]] = defaultdict(list)

    def subscribe(self, event_type: Type[EventT], handler: Callable[[EventT], None]) -> None:
        self._subscribers[event_type].append(handler)

    def publish(self, event) -> None:
        for handler in self._subscribers[type(event)]:
            handler(event)
