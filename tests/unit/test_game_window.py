from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import FrameTickEvent
from kungfu_chess.graphics.game_window import GameWindow


class FakeCanvas:
    def __init__(self):
        self.show_frame_calls = []

    def show_frame(self, window_name, delay):
        self.show_frame_calls.append((window_name, delay))


class FakeEngine:
    def __init__(self):
        self.wait_calls = []

    def wait(self, ms):
        self.wait_calls.append(ms)

    def snapshot(self):
        return "a-snapshot-sentinel"


class FakeRenderer:
    def __init__(self, left_panel_width_px=0):
        self.render_calls = []
        self.left_panel_width_px = left_panel_width_px

    def render(self, snapshot, now_ms):
        self.render_calls.append((snapshot, now_ms))
        return FakeCanvas()


class FakeInputRouter:
    def __init__(self):
        self.tick_calls = []
        self.on_mouse_down_calls = []

    def tick(self, now_ms):
        self.tick_calls.append(now_ms)

    def on_mouse_down(self, x, y, now_ms):
        self.on_mouse_down_calls.append((x, y, now_ms))


class FakeImgCls:
    """Stand-in for the Img class's 4 static window methods - lets
    GameWindow be tested with zero real cv2/OS window involved."""

    def __init__(self, is_window_open_sequence):
        self._is_window_open_sequence = list(is_window_open_sequence)
        self.set_mouse_callback_calls = []
        self.close_calls = []

    def set_mouse_callback(self, window_name, callback):
        self.set_mouse_callback_calls.append((window_name, callback))

    def is_window_open(self, window_name):
        return self._is_window_open_sequence.pop(0)

    def close(self, window_name):
        self.close_calls.append(window_name)


def _build(clock_values, is_window_open_sequence=(), left_panel_width_px=0, bus=None):
    values = iter(clock_values)
    engine = FakeEngine()
    renderer = FakeRenderer(left_panel_width_px=left_panel_width_px)
    input_router = FakeInputRouter()
    img_cls = FakeImgCls(is_window_open_sequence)
    window = GameWindow(engine, renderer, input_router,
                         clock=lambda: next(values), img_cls=img_cls, bus=bus)
    return window, engine, renderer, input_router, img_cls


def test_first_step_advances_the_engine_by_zero_since_there_is_no_prior_reading():
    window, engine, renderer, input_router, img_cls = _build(clock_values=[1000])

    window.step()

    assert engine.wait_calls == [0]


def test_second_step_advances_the_engine_by_the_wall_clock_delta():
    window, engine, renderer, input_router, img_cls = _build(clock_values=[1000, 1250])

    window.step()
    window.step()

    assert engine.wait_calls == [0, 250]


def test_wait_tick_and_render_all_receive_the_identical_now_ms_within_one_step():
    window, engine, renderer, input_router, img_cls = _build(clock_values=[1000, 1400])

    window.step()
    window.step()

    # After two steps the mirrored engine clock is 0 + (1400-1000) = 400.
    assert input_router.tick_calls[-1] == 400
    assert renderer.render_calls[-1][1] == 400


def test_render_receives_the_engine_snapshot_and_returns_its_canvas_to_show_frame():
    window, engine, renderer, input_router, img_cls = _build(clock_values=[1000])

    canvas = window.step()

    assert renderer.render_calls[0][0] == "a-snapshot-sentinel"
    assert canvas.show_frame_calls == [("KungFuChess", 1)]


def test_mouse_callback_is_registered_only_once_after_the_first_frame():
    window, engine, renderer, input_router, img_cls = _build(clock_values=[1000, 1100, 1200])

    window.step()
    window.step()
    window.step()

    assert len(img_cls.set_mouse_callback_calls) == 1
    assert img_cls.set_mouse_callback_calls[0][0] == "KungFuChess"


def test_a_simulated_click_is_stamped_with_that_frames_engine_clock_value():
    window, engine, renderer, input_router, img_cls = _build(clock_values=[1000, 1300])

    window.step()  # registers the callback, engine clock is now 0
    window.step()  # engine clock is now 0 + 300 = 300

    _, captured_callback = img_cls.set_mouse_callback_calls[0]
    captured_callback(event=1, x=42, y=7, flags=0, param=None)  # 1 == LBUTTONDOWN

    assert input_router.on_mouse_down_calls == [(42, 7, 300)]


def test_a_click_has_the_renderers_left_panel_width_subtracted_before_reaching_input_router():
    # GameRenderer's canvas now has a side panel left of the board, so a
    # raw window click's x must be shifted back to board-relative pixels
    # before InputRouter (which knows nothing about panels) ever sees it.
    window, engine, renderer, input_router, img_cls = _build(
        clock_values=[1000], left_panel_width_px=150)

    window.step()
    _, captured_callback = img_cls.set_mouse_callback_calls[0]
    captured_callback(event=1, x=200, y=7, flags=0, param=None)  # 1 == LBUTTONDOWN

    assert input_router.on_mouse_down_calls == [(50, 7, 0)]


def test_a_simulated_non_left_button_event_is_ignored():
    window, engine, renderer, input_router, img_cls = _build(clock_values=[1000])

    window.step()
    _, captured_callback = img_cls.set_mouse_callback_calls[0]
    captured_callback(event=999, x=1, y=1, flags=0, param=None)  # not LBUTTONDOWN

    assert input_router.on_mouse_down_calls == []


def test_without_bus_step_behaves_exactly_as_before():
    window, engine, renderer, input_router, img_cls = _build(clock_values=[1000])

    window.step()

    assert renderer.render_calls == [("a-snapshot-sentinel", 0)]


def test_with_bus_frame_tick_event_is_published_alongside_the_direct_render_call():
    bus = EventBus()
    received = []
    bus.subscribe(FrameTickEvent, received.append)
    window, engine, renderer, input_router, img_cls = _build(clock_values=[1000, 1300], bus=bus)

    window.step()
    window.step()

    # The direct render() call (dual path, not yet removed) still ran too.
    assert renderer.render_calls == [("a-snapshot-sentinel", 0), ("a-snapshot-sentinel", 300)]
    assert received == [
        FrameTickEvent(snapshot="a-snapshot-sentinel", now_ms=0),
        FrameTickEvent(snapshot="a-snapshot-sentinel", now_ms=300),
    ]


def test_run_calls_step_exactly_once_per_true_in_the_is_window_open_sequence():
    # is_window_open is checked *after* each step(), so a 3-long
    # [True, True, False] sequence means exactly 3 step() calls.
    window, engine, renderer, input_router, img_cls = _build(
        clock_values=[1000, 1010, 1020],
        is_window_open_sequence=[True, True, False],
    )

    window.run()

    assert len(renderer.render_calls) == 3
    assert img_cls.close_calls == ["KungFuChess"]
