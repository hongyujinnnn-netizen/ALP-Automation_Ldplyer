from __future__ import annotations


class TaskStateMachine:
    """Small shared state helper for automation phases."""

    VALID_STATES = {
        "Idle",
        "Queued",
        "Starting",
        "Waiting",
        "Active",
        "Preparing",
        "Ready",
        "Running",
        "Completed",
        "Attention",
        "Closing",
    }

    def normalize(self, state: str) -> str:
        normalized = (state or "").strip().title()
        return normalized if normalized in self.VALID_STATES else "Idle"
