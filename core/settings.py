from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict


class SettingsError(RuntimeError):
    """Raised when loading or saving a settings file fails."""


@dataclass(slots=True)
class AppSettings:
    """Persisted UI preferences for the LDManager application."""

    parallel_ld: int = 2
    boot_delay: int = 10
    task_duration: int = 15
    max_videos: int = 2
    start_same_time: bool = False
    use_content_queue: bool = True

    @classmethod
    def from_dict(cls, raw: Dict) -> "AppSettings":
        try:
            return cls(
                parallel_ld=int(raw.get("parallel_ld", cls.parallel_ld)),
                boot_delay=int(raw.get("boot_delay", cls.boot_delay)),
                task_duration=int(raw.get("task_duration", cls.task_duration)),
                max_videos=int(raw.get("max_videos", cls.max_videos)),
                start_same_time=bool(raw.get("start_same_time", cls.start_same_time)),
                use_content_queue=bool(raw.get("use_content_queue", cls.use_content_queue)),
            )
        except (TypeError, ValueError) as exc:
            raise SettingsError(f"Invalid value in application settings: {exc}") from exc

    def to_dict(self) -> Dict:
        return asdict(self)


def _default_schedule_days() -> Dict[str, bool]:
    return {
        "Monday": False,
        "Tuesday": False,
        "Wednesday": False,
        "Thursday": False,
        "Friday": False,
        "Saturday": False,
        "Sunday": False,
    }


@dataclass(slots=True)
class ScheduleSettings:
    """Scheduling preferences for automated runs."""

    schedule_time: str = "09:00"
    schedule_daily: bool = True
    schedule_weekly: bool = False
    schedule_repeat_hours: int = 0
    schedule_days: Dict[str, bool] = field(default_factory=_default_schedule_days)

    @classmethod
    def from_dict(cls, raw: Dict) -> "ScheduleSettings":
        try:
            days = dict(_default_schedule_days())
            raw_days = raw.get("schedule_days") or {}
            for name, value in raw_days.items():
                if name in days:
                    days[name] = bool(value)

            return cls(
                schedule_time=str(raw.get("schedule_time", cls.schedule_time)),
                schedule_daily=bool(raw.get("schedule_daily", cls.schedule_daily)),
                schedule_weekly=bool(raw.get("schedule_weekly", cls.schedule_weekly)),
                schedule_repeat_hours=int(raw.get("schedule_repeat_hours", cls.schedule_repeat_hours)),
                schedule_days=days,
            )
        except (TypeError, ValueError) as exc:
            raise SettingsError(f"Invalid value in schedule settings: {exc}") from exc

    def to_dict(self) -> Dict:
        data = asdict(self)
        # Dataclasses + slots still return shallow copy so safe to reuse
        return data


def load_app_settings(path: Path) -> AppSettings:
    if not path.exists():
        return AppSettings()

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SettingsError(f"Could not read application settings: {exc}") from exc

    return AppSettings.from_dict(raw)


def save_app_settings(path: Path, settings: AppSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(settings.to_dict(), handle, indent=4, ensure_ascii=False)
    except OSError as exc:
        raise SettingsError(f"Could not write application settings: {exc}") from exc


def load_schedule_settings(path: Path) -> ScheduleSettings:
    if not path.exists():
        return ScheduleSettings()

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SettingsError(f"Could not read schedule settings: {exc}") from exc

    return ScheduleSettings.from_dict(raw)


def save_schedule_settings(path: Path, settings: ScheduleSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(settings.to_dict(), handle, indent=4, ensure_ascii=False)
    except OSError as exc:
        raise SettingsError(f"Could not write schedule settings: {exc}") from exc
