from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(slots=True)
class _TaskSample:
    id: str
    start_time: float


# ==================== PERFORMANCE MONITOR ====================
class PerformanceMonitor:
    """
    Lightweight in‑memory tracker for automation performance.

    It is intentionally simple and process‑local; callers are expected to
    periodically read `get_stats()` for UI display rather than persist it.
    """

    def __init__(self) -> None:
        self.metrics: Dict[str, object] = {
            "task_duration": [],  # type: ignore[assignment]
            "success_rate": [],  # type: ignore[assignment]
            "device_uptime": [],  # reserved for future use
            "tasks_completed": 0,
            "tasks_failed": 0,
        }
        self._current_task: _TaskSample | None = None

    def start_task_timer(self, task_id: str) -> None:
        """Mark the beginning of a logical batch/task."""
        self._current_task = _TaskSample(id=str(task_id), start_time=time.time())

    def end_task_timer(self, success: bool = True) -> None:
        """
        Finish the currently tracked task and record duration + outcome.
        """
        if self._current_task is None:
            return

        duration = time.time() - self._current_task.start_time
        durations: List[float] = self.metrics["task_duration"]  # type: ignore[assignment]
        successes: List[bool] = self.metrics["success_rate"]  # type: ignore[assignment]

        durations.append(duration)
        successes.append(success)

        if success:
            self.metrics["tasks_completed"] = int(self.metrics["tasks_completed"]) + 1
        else:
            self.metrics["tasks_failed"] = int(self.metrics["tasks_failed"]) + 1

        self._current_task = None

    def get_average_duration(self) -> float:
        durations: List[float] = self.metrics["task_duration"]  # type: ignore[assignment]
        if not durations:
            return 0.0
        return float(sum(durations) / len(durations))

    def get_success_rate(self) -> float:
        samples: List[bool] = self.metrics["success_rate"]  # type: ignore[assignment]
        if not samples:
            return 0.0
        return float(sum(1 for s in samples if s) / len(samples) * 100.0)

    def get_total_tasks(self) -> int:
        return int(self.metrics["tasks_completed"]) + int(self.metrics["tasks_failed"])

    def get_stats(self) -> Dict[str, float | int]:
        """
        Return a snapshot suitable for UI display.
        """
        return {
            "total_tasks": self.get_total_tasks(),
            "success_rate": self.get_success_rate(),
            "avg_duration": self.get_average_duration(),
            "completed": int(self.metrics["tasks_completed"]),
            "failed": int(self.metrics["tasks_failed"]),
        }