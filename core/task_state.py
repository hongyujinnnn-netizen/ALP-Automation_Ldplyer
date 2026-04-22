"""Per-device task lifecycle state model.

This module gives the previously-untyped ``state="Running"`` strings a
real enum so future code can write::

    self.push_runtime_state(name, state=TaskState.RUNNING, ...)

while the existing ~40 call sites that still emit raw strings continue
to work unchanged. The enum's ``.value`` is the exact string vocabulary
the GUI already renders, so nothing downstream has to change.

Why this is *documentation + optional typing* rather than enforcement:
    Current handlers make legitimate jumps between states (e.g. reels
    reports ``Completed`` without visiting ``Ready`` first, because the
    reels pipeline has its own sub-phases). A strict runtime transition
    check would either reject valid flows or collapse into a permissive
    noop. The transition table below is kept as a map so it can drive
    future UI hints or analytics without forcing today's handlers to
    change.

Mapping notes (names in the refactor brief vs. existing code):
    * ``failed`` → ``Attention`` — the codebase has always used
      "Attention" for error/user-intervention states, and the GUI
      styles it accordingly. Renaming would ripple into tests, status
      widgets, and user-visible labels. The enum member is called
      ``FAILED`` (brief's semantic name) with ``.value = "Attention"``
      (existing string). ``ATTENTION`` is kept as an alias so handlers
      that read more naturally with the old name stay readable.
    * Additional states present in the code but not listed in the
      brief — ``Queued``, ``Waiting``, ``Active``, ``Preparing`` — are
      kept because the GUI already distinguishes them.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet


class TaskState(str, Enum):
    """Canonical per-device lifecycle states.

    Inheriting from ``str`` means ``TaskState.RUNNING == "Running"`` and
    the member can be passed to any API that accepts a string without
    conversion. That is how this enum is introduced without touching
    existing call sites.
    """

    IDLE = "Idle"
    QUEUED = "Queued"
    STARTING = "Starting"
    WAITING = "Waiting"
    ACTIVE = "Active"
    PREPARING = "Preparing"
    READY = "Ready"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Attention"
    CLOSING = "Closing"

    @classmethod
    def from_string(cls, value: str | "TaskState" | None) -> "TaskState":
        """Normalize arbitrary input to a ``TaskState`` member.

        Accepts the exact string value (``"Running"``), any case
        variant (``"running"``), an already-``TaskState`` member, or
        ``None``. Unknown input falls back to :attr:`IDLE`, matching
        the behavior of :class:`core.state_machine.TaskStateMachine`.
        """
        if isinstance(value, cls):
            return value
        normalized = (value or "").strip().title()
        try:
            return cls(normalized)
        except ValueError:
            return cls.IDLE


# Alias for handlers that have historically used "attention" as the
# semantic name. Both refer to the same member (``.value == "Attention"``).
ATTENTION = TaskState.FAILED


#: Expected forward transitions. Informational only — not enforced at
#: runtime. Back-edges (any → IDLE, any → FAILED) are implicit.
TRANSITIONS: Dict[TaskState, FrozenSet[TaskState]] = {
    TaskState.IDLE: frozenset({TaskState.QUEUED, TaskState.STARTING}),
    TaskState.QUEUED: frozenset({TaskState.STARTING, TaskState.IDLE}),
    TaskState.STARTING: frozenset({TaskState.WAITING, TaskState.FAILED}),
    TaskState.WAITING: frozenset({TaskState.ACTIVE, TaskState.FAILED}),
    TaskState.ACTIVE: frozenset({TaskState.PREPARING, TaskState.FAILED}),
    TaskState.PREPARING: frozenset({TaskState.READY, TaskState.FAILED}),
    TaskState.READY: frozenset({TaskState.RUNNING, TaskState.FAILED}),
    TaskState.RUNNING: frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.CLOSING}),
    TaskState.COMPLETED: frozenset({TaskState.CLOSING, TaskState.IDLE}),
    TaskState.FAILED: frozenset({TaskState.CLOSING, TaskState.IDLE}),
    TaskState.CLOSING: frozenset({TaskState.IDLE}),
}


def is_terminal(state: TaskState) -> bool:
    """Return True if no further forward transitions are expected."""
    return state in {TaskState.IDLE, TaskState.COMPLETED, TaskState.FAILED}


def can_transition(current: TaskState, target: TaskState) -> bool:
    """Return True if ``target`` is listed as an expected successor.

    Callers may use this to warn on unexpected transitions, but the
    state machine itself does not reject them — handlers are allowed
    to skip states when their workflow legitimately does so.
    """
    if target is TaskState.IDLE or target is TaskState.FAILED:
        return True
    return target in TRANSITIONS.get(current, frozenset())
