from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, List


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
    # Two-letter ISO country codes to block when detected as the host's
    # public IP country. If the country is blocked, automation will not start.
    blocked_countries: List[str] = field(
        default_factory=lambda: [
            "US",  # United States
            "KH",  # Cambodia / Khmer
            "CN",  # China
            "TH",  # Thailand
            "VN",  # Vietnam
            "PH",  # Philippines
            "ID",  # Indonesia
            "MY",  # Malaysia
            "LA",  # Laos
            "MM",  # Myanmar
        ]
    )

    @classmethod
    def from_dict(cls, raw: Dict) -> "AppSettings":
        try:
            raw_blocked = raw.get("blocked_countries")
            if isinstance(raw_blocked, list):
                blocked_countries = [str(code).upper() for code in raw_blocked if code]
            elif isinstance(raw_blocked, str):
                blocked_countries = [part.strip().upper() for part in raw_blocked.split(",") if part.strip()]
            else:
                blocked_countries = cls.blocked_countries  # type: ignore[attr-defined]

            return cls(
                parallel_ld=int(raw.get("parallel_ld", cls.parallel_ld)),
                boot_delay=int(raw.get("boot_delay", cls.boot_delay)),
                task_duration=int(raw.get("task_duration", cls.task_duration)),
                max_videos=int(raw.get("max_videos", cls.max_videos)),
                start_same_time=bool(raw.get("start_same_time", cls.start_same_time)),
                use_content_queue=bool(raw.get("use_content_queue", cls.use_content_queue)),
                blocked_countries=blocked_countries,
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
    _atomic_write_json(path, settings.to_dict())


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
    _atomic_write_json(path, settings.to_dict())


def _atomic_write_json(path: Path, data: Any) -> None:
    """
    Safely write JSON to disk using a temp file + atomic replace.

    This greatly reduces the chance of corrupting JSON files if the
    process is interrupted during a write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=4, ensure_ascii=False)
        os.replace(tmp_path, path)
    except OSError as exc:
        # Best-effort cleanup of partial temp file
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise SettingsError(f"Could not write JSON settings: {exc}") from exc
