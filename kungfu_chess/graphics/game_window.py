"""
GameWindow: owns the real on-screen game loop. It is the one place that
turns wall-clock time into the single now_ms reading that GameEngine.wait,
InputRouter.tick and GameRenderer.render all share for one frame, and the
one place that wires a real OS mouse click into InputRouter.on_mouse_down.

WHY GameEngine's OWN CLOCK, NOT WALL-CLOCK TIME, FEEDS THE RENDERER:
GameEngine.wait(ms) takes a *delta* and advances an internal clock that
starts at 0; GameSnapshot.motions timestamps (start_ms/arrival_ms) are
recorded on that same internal clock. GameRenderer.render(snapshot, now_ms)
interpolates motion progress using those timestamps, so now_ms has to be on
that identical timescale - raw wall-clock milliseconds would desync it
immediately. GameWindow is the only place that bridges the two: it reads
wall time once per frame, turns it into a delta, and accumulates that delta
into its own mirrored "engine clock" - the same value then goes to
engine.wait(), input_router.tick() and renderer.render() for that frame,
so none of the three can ever drift relative to each other.
"""

from __future__ import annotations

import time
from typing import Callable, Optional, Type

from kungfu_chess.bus.event_bus import EventBus
from kungfu_chess.bus.events import FrameTickEvent
from kungfu_chess.graphics.img import Img

# Mirrors cv2.EVENT_LBUTTONDOWN's numeric value. Kept as a local constant
# instead of `import cv2` so "cv2." stays confined to img.py.
_EVENT_LBUTTONDOWN = 1


class GameWindow:
    def __init__(self, engine, renderer, input_router,
                 clock: Optional[Callable[[], int]] = None,
                 img_cls: Type[Img] = Img,
                 window_name: str = "KungFuChess",
                 frame_delay_ms: int = 1,
                 bus: Optional[EventBus] = None):
        self._engine = engine
        self._renderer = renderer
        self._input_router = input_router
        self._clock = clock if clock is not None else self._default_clock
        self._img_cls = img_cls
        self._window_name = window_name
        self._frame_delay_ms = frame_delay_ms
        self._bus = bus

        self._engine_clock_ms = 0
        self._last_wall_ms: Optional[int] = None
        self._mouse_registered = False
        self._last_canvas: Optional[Img] = None

        if self._bus is not None:
            self._bus.subscribe(FrameTickEvent, self._on_frame_tick)

    @staticmethod
    def _default_clock() -> int:
        return int(time.time() * 1000)

    def step(self) -> Img:
        """One frame's worth of work: advance the shared clock, let a
        pending single click commit if its window elapsed, advance the
        engine, then trigger a render. Returns the drawn canvas so it can
        be asserted on directly in a test, without needing a real window.

        WHY RENDERING HAPPENS THROUGH _on_frame_tick RATHER THAN A DIRECT
        renderer.render() CALL HERE WHEN A BUS IS GIVEN:
        This is the message-bus migration's switch-over step - the direct
        call from the dual-path stage is gone; publishing FrameTickEvent
        is now the only trigger. EventBus.publish() is synchronous, so
        _on_frame_tick still runs inside this same step() call and
        self._last_canvas is already set by the time step() returns -
        no behavior changes, only how the render gets triggered. The
        no-bus fallback below exists only for callers/tests that
        construct a bus-less GameWindow directly; the real app (app.py)
        always supplies a bus after this step.
        """
        wall_now = self._clock()
        delta_ms = 0 if self._last_wall_ms is None else wall_now - self._last_wall_ms
        self._last_wall_ms = wall_now
        self._engine_clock_ms += delta_ms

        self._engine.wait(delta_ms)
        self._input_router.tick(self._engine_clock_ms)

        snapshot = self._engine.snapshot()

        if self._bus is not None:
            self._bus.publish(FrameTickEvent(snapshot=snapshot, now_ms=self._engine_clock_ms))
            return self._last_canvas

        return self._render_and_show(snapshot, self._engine_clock_ms)

    def _on_frame_tick(self, event: FrameTickEvent) -> None:
        self._last_canvas = self._render_and_show(event.snapshot, event.now_ms)

    def _render_and_show(self, snapshot, now_ms: int) -> Img:
        canvas = self._renderer.render(snapshot, now_ms)
        canvas.show_frame(self._window_name, self._frame_delay_ms)
        self._ensure_mouse_callback_registered()
        return canvas

    def _ensure_mouse_callback_registered(self) -> None:
        """cv2.setMouseCallback requires the named window to already
        exist, and the window is only created by the first show_frame()
        call above - so registration is deferred to right after that
        first frame, not done eagerly in __init__.
        """
        if not self._mouse_registered:
            self._img_cls.set_mouse_callback(self._window_name, self._on_mouse)
            self._mouse_registered = True

    def _on_mouse(self, event, x, y, flags, param) -> None:
        """The raw window-toolkit mouse callback. Reuses this frame's
        already-computed self._engine_clock_ms instead of taking a second,
        independent clock reading, so a click during frame N is always
        timestamped with frame N's one clock reading - never a value that
        could drift from what wait()/tick()/render() just used.

        `x` is subtracted by the renderer's own left_panel_width_px before
        it ever reaches InputRouter, since the renderer's canvas now has a
        side panel sitting left of the board (x=0 in the window is no
        longer x=0 on the board). This keeps InputRouter itself completely
        unaware of panels - it still only ever sees board-relative pixels,
        exactly as BoardMapper/Controller downstream already expect - and
        keeps the panel-layout decision owned by GameRenderer alone,
        GameWindow just asks its renderer for the number rather than
        hard-coding it here.
        """
        if event == _EVENT_LBUTTONDOWN:
            board_x = x - self._renderer.left_panel_width_px
            self._input_router.on_mouse_down(board_x, y, self._engine_clock_ms)

    def run(self) -> None:
        """The actual infinite loop. Effectively untestable for real cv2
        semantics (like main()'s event loop in most GUI apps) - step() is
        the tested unit; this just repeats it until the window is closed.
        Do-while shaped, not a pre-check while, because the window does
        not exist yet before the first step() runs.
        """
        while True:
            self.step()
            if not self._img_cls.is_window_open(self._window_name):
                break
        self._img_cls.close(self._window_name)
