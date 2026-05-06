from __future__ import annotations

import time
from typing import List


# ==================== RATE LIMITER ====================
class RateLimiter:
    """
    Simple sliding‑window rate limiter used by task handlers.

    The limiter is intentionally generic; callers can pass any action_type
    label for logging/segmentation purposes if needed in the future.
    """

    def __init__(self, max_actions_per_hour: int = 100) -> None:
        self.max_actions: int = int(max_actions_per_hour)
        self.action_log: List[float] = []

    def _prune(self) -> None:
        """Drop timestamps older than one hour."""
        one_hour_ago = time.time() - 3600.0
        self.action_log = [t for t in self.action_log if t > one_hour_ago]

    def can_perform_action(self, action_type: str) -> bool:  # noqa: ARG002 - future use
        """
        Register a potential action and return True if it stays within budget.

        The action is recorded only when allowed.
        """
        self._prune()

        if len(self.action_log) < self.max_actions:
            self.action_log.append(time.time())
            return True
        return False

    def get_remaining_actions(self) -> int:
        """Return how many actions are still allowed in the current hour."""
        self._prune()
        return max(0, self.max_actions - len(self.action_log))

    def get_wait_time(self) -> float:
        """
        Approximate number of seconds until *some* capacity is available.
        """
        if not self.action_log:
            return 0.0

        self._prune()

        if len(self.action_log) < self.max_actions:
            return 0.0

        # Time until the oldest recorded action falls out of the one‑hour window.
        oldest_action = min(self.action_log)
        return max(0.0, (oldest_action + 3600.0) - time.time())
