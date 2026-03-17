from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class SchedulerDecision:
    should_run: bool
    next_time: str | None = None


class SchedulerService:
    """Extracts schedule decision logic away from the GUI thread."""

    def should_run(
        self,
        now: datetime,
        schedule_time: str,
        schedule_daily: bool,
        schedule_days: dict[str, bool],
        is_running: bool,
    ) -> bool:
        if is_running:
            return False
        if now.strftime("%H:%M") != schedule_time:
            return False
        if schedule_daily:
            return True
        return bool(schedule_days.get(now.strftime("%A"), False))

    def apply_repeat_interval(self, now: datetime, repeat_hours: int) -> SchedulerDecision:
        if repeat_hours <= 0:
            return SchedulerDecision(should_run=True, next_time=None)
        next_time = now.replace(second=0, microsecond=0)
        from datetime import timedelta

        next_time = next_time + timedelta(hours=repeat_hours)
        return SchedulerDecision(should_run=True, next_time=next_time.strftime("%H:%M"))
