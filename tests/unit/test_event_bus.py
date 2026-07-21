from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import (
    MouseClickEvent,
    MouseJumpEvent,
    MoveRequestedEvent,
    JumpRequestedEvent,
    MoveCompletedEvent,
    FrameTickEvent,
)
from kungfu_chess.model.position import Position


def test_subscriber_receives_published_event():
    bus = EventBus()
    received = []
    bus.subscribe(MouseClickEvent, received.append)

    event = MouseClickEvent(x=10, y=20)
    bus.publish(event)

    assert received == [event]


def test_publish_with_no_subscribers_does_nothing():
    bus = EventBus()
    bus.publish(MouseClickEvent(x=1, y=2))  # must not raise


def test_multiple_subscribers_all_receive_the_event():
    bus = EventBus()
    first, second = [], []
    bus.subscribe(MouseJumpEvent, first.append)
    bus.subscribe(MouseJumpEvent, second.append)

    event = MouseJumpEvent(x=5, y=6)
    bus.publish(event)

    assert first == [event]
    assert second == [event]


def test_subscribers_only_receive_their_own_event_type():
    bus = EventBus()
    move_events, jump_events = [], []
    bus.subscribe(MoveRequestedEvent, move_events.append)
    bus.subscribe(JumpRequestedEvent, jump_events.append)

    bus.publish(MoveRequestedEvent(source=Position(0, 0), destination=Position(0, 1)))

    assert len(move_events) == 1
    assert jump_events == []


def test_move_completed_event_carries_source_and_destination():
    bus = EventBus()
    received = []
    bus.subscribe(MoveCompletedEvent, received.append)

    event = MoveCompletedEvent(source=Position(1, 1), destination=Position(2, 1))
    bus.publish(event)

    assert received[0].source == Position(1, 1)
    assert received[0].destination == Position(2, 1)
    assert received[0].is_jump is False


def test_frame_tick_event_carries_snapshot_and_time():
    bus = EventBus()
    received = []
    bus.subscribe(FrameTickEvent, received.append)

    fake_snapshot = object()
    bus.publish(FrameTickEvent(snapshot=fake_snapshot, now_ms=1234))

    assert received[0].snapshot is fake_snapshot
    assert received[0].now_ms == 1234
