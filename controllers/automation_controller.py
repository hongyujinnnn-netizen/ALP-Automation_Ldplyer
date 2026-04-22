"""Automation lifecycle controller.

Owns the run/pause state for an automation batch and exposes an API
(``start`` / ``pause`` / ``resume`` / ``toggle_pause`` / ``stop``) that the
GUI — or any other driver — can call without knowing about Tk widgets.

UI reacts to state transitions via small callback hooks registered on the
controller. The controller itself never imports ``gui.*``.

Why a controller (and not just methods on ``LDManagerApp``):
    * ``LDManagerApp`` already exceeds 2700 lines; lifecycle code is
      tangled with widget manipulation and batch orchestration.
    * Lifecycle state (``running_event``, ``pause_event``) is a coherent
      unit that can be reasoned about and tested without a Tk root.
    * A non-GUI driver (scheduler, CLI) needs the same state surface.

This is an incremental extraction. The heavy batch-orchestration body
(building the ``TaskHandlerContext``, spawning the worker thread, running
``MainWindow.main()``) still lives in ``LDManagerApp`` for now; moving it
is the job of Step 5.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, List, Protocol


class _Runnable(Protocol):
    """Minimal surface a batch runner must expose."""

    def main(self) -> Any: ...


class AutomationState(str, Enum):
    """Coarse lifecycle states visible to UI listeners.

    Kept intentionally small for Step 4. A finer-grained state model
    (``starting``, ``ready``, ``completed``, ``failed``, ``closing``) is
    the subject of Phase 3 Step 6.
    """

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


StateListener = Callable[[AutomationState], None]


@dataclass
class AutomationController:
    """Owns automation lifecycle state.

    The two ``threading.Event`` objects retain the exact semantics used
    throughout the codebase:

    * ``running_event`` — **set** means "automation batch is active".
      Worker loops poll ``running_event.is_set()`` and exit when cleared.
    * ``pause_event`` — **set** means "not paused" (workers may proceed).
      Cleared means "paused"; workers block on it.

    These semantics are preserved verbatim so every existing call site
    that reads the events directly continues to work during the
    transition period.
    """

    running_event: threading.Event = field(default_factory=threading.Event)
    pause_event: threading.Event = field(default_factory=threading.Event)
    _listeners: List[StateListener] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        # Match historical init: pause_event starts set (= not paused).
        self.pause_event.set()

    # -- observation ------------------------------------------------------

    def add_state_listener(self, listener: StateListener) -> None:
        """Register a callback fired on every state transition.

        Listeners are invoked synchronously on the caller's thread. UI
        listeners should marshal back to the Tk main loop themselves
        (e.g. via ``root.after``) if called from a worker thread.
        """
        self._listeners.append(listener)

    def _notify(self, state: AutomationState) -> None:
        for listener in list(self._listeners):
            try:
                listener(state)
            except Exception:
                # A broken listener must not break lifecycle transitions.
                continue

    # -- queries ----------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self.running_event.is_set()

    @property
    def is_paused(self) -> bool:
        return self.running_event.is_set() and not self.pause_event.is_set()

    @property
    def state(self) -> AutomationState:
        if not self.running_event.is_set():
            return AutomationState.IDLE
        if not self.pause_event.is_set():
            return AutomationState.PAUSED
        return AutomationState.RUNNING

    # -- transitions ------------------------------------------------------

    def start(self) -> None:
        """Mark a batch as running. Idempotent."""
        self.running_event.set()
        self.pause_event.set()
        self._notify(AutomationState.RUNNING)

    def pause(self) -> None:
        """Pause a running batch. No-op if not running or already paused."""
        if not self.running_event.is_set() or not self.pause_event.is_set():
            return
        self.pause_event.clear()
        self._notify(AutomationState.PAUSED)

    def resume(self) -> None:
        """Resume from pause. No-op if not paused."""
        if not self.running_event.is_set() or self.pause_event.is_set():
            return
        self.pause_event.set()
        self._notify(AutomationState.RUNNING)

    def toggle_pause(self) -> AutomationState:
        """Flip between ``RUNNING`` and ``PAUSED``. Returns the new state."""
        if self.pause_event.is_set():
            self.pause()
        else:
            self.resume()
        return self.state

    def stop(self) -> None:
        """Stop the batch. Always clears pause so blocked workers unblock."""
        was_running = self.running_event.is_set()
        self.running_event.clear()
        self.pause_event.set()
        if was_running:
            self._notify(AutomationState.IDLE)

    # -- batch execution --------------------------------------------------

    def run_batch(
        self,
        runner: _Runnable,
        on_error: Callable[[BaseException], None] | None = None,
        on_completed: Callable[[bool], None] | None = None,
    ) -> bool:
        """Execute ``runner.main()`` inside the lifecycle bookkeeping.

        The caller decides threading — this method only runs on whatever
        thread it is invoked from. GUI drivers should call it from a
        worker thread so the Tk main loop is not blocked.

        Args:
            runner: object exposing ``main()`` (currently ``MainWindow``).
            on_error: optional callback receiving any exception raised by
                the runner. Dialogs live in the GUI; the controller only
                hands the exception over.
            on_completed: optional callback receiving a bool indicating
                whether the batch ran to completion without being stopped
                (``running_event`` still set when ``main()`` returned).

        Returns ``True`` if the batch completed normally, ``False``
        otherwise. The controller always calls :meth:`stop` in its
        ``finally`` block so UI listeners observe the IDLE transition.
        """
        completed_normally = False
        try:
            runner.main()
            completed_normally = self.running_event.is_set()
        except BaseException as exc:
            if on_error is not None:
                on_error(exc)
            else:
                raise
            return False
        finally:
            self.stop()
        if on_completed is not None:
            on_completed(completed_normally)
        return completed_normally
