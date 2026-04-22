from __future__ import annotations

from core.task_state import TaskState


class TaskStateMachine:
    """Small shared state helper for automation phases.

    The canonical state set now lives on :class:`core.task_state.TaskState`.
    This class is kept as a thin adapter so existing callers and tests
    that go through ``TaskStateMachine().normalize(...)`` continue to
    work without change.
    """

    #: Backwards-compatible view of the valid state strings. Some tests
    #: and external consumers read this attribute, so it stays a set of
    #: plain strings.
    VALID_STATES = {state.value for state in TaskState}

    def normalize(self, state) -> str:
        """Return the canonical *string* form of ``state``.

        Accepts a string in any case or a :class:`TaskState` member.
        Unknown input falls back to ``"Idle"``.
        """
        return TaskState.from_string(state).value
