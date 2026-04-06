from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, List

from core.email_models import EmailAccountConfig, OTPRequest


class SettingsError(RuntimeError):
    """Raised when loading or saving a settings file fails."""


@dataclass(slots=True)
class AppSettings:
    """Persisted UI preferences for the LDManager application."""

    parallel_ld: int = 2
    boot_delay: int = 10
    task_duration: int = 15
    max_videos: int = 2
    page_per_account: int = 2
    start_same_time: bool = False
    use_content_queue: bool = True
    auto_arrange_ld: bool = False
    auto_shutdown_pc: bool = False
    task_type: str = "scroll"
    task_template: str = "custom"
    scroll_after_post: bool = True
    clear_cache: bool = True
    verify_account: bool = True
    reg_contact_mode: str = "random_phone"
    reg_contact_value: str = ""
    reg_phone_prefix: str = "+1"
    email_provider: str = "yandex"
    email_address: str = ""
    email_app_password: str = ""
    email_imap_server: str = "imap.yandex.com"
    email_imap_port: int = 993
    email_mailbox: str = "INBOX"
    email_use_ssl: bool = True
    email_unread_only: bool = True
    email_sender_filter: str = ""
    email_subject_filter: str = ""
    email_timeout_seconds: int = 90
    email_poll_interval_seconds: int = 5
    email_mark_as_seen: bool = False
    ld_groups: Dict[str, List[str]] = field(default_factory=dict)
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
            raw_groups = raw.get("ld_groups") or {}
            ld_groups: Dict[str, List[str]] = {}
            if isinstance(raw_groups, dict):
                for group_name, members in raw_groups.items():
                    cleaned_name = str(group_name).strip()
                    if not cleaned_name:
                        continue
                    if isinstance(members, list):
                        cleaned_members = []
                        for member in members:
                            text = str(member).strip()
                            if text and text not in cleaned_members:
                                cleaned_members.append(text)
                        ld_groups[cleaned_name] = cleaned_members

            raw_blocked = raw.get("blocked_countries")
            if isinstance(raw_blocked, list):
                blocked_countries = [str(code).upper() for code in raw_blocked if code]
            elif isinstance(raw_blocked, str):
                blocked_countries = [part.strip().upper() for part in raw_blocked.split(",") if part.strip()]
            else:
                blocked_countries = cls.blocked_countries  # type: ignore[attr-defined]

            provider = str(raw.get("email_provider", cls.email_provider)).strip().lower() or "yandex"
            provider_defaults = EmailAccountConfig(provider=provider).with_provider_defaults()
            request_defaults = OTPRequest()

            return cls(
                parallel_ld=int(raw.get("parallel_ld", cls.parallel_ld)),
                boot_delay=int(raw.get("boot_delay", cls.boot_delay)),
                task_duration=int(raw.get("task_duration", cls.task_duration)),
                max_videos=int(raw.get("max_videos", cls.max_videos)),
                page_per_account=int(raw.get("page_per_account", cls.page_per_account)),
                start_same_time=bool(raw.get("start_same_time", cls.start_same_time)),
                use_content_queue=bool(raw.get("use_content_queue", cls.use_content_queue)),
                auto_arrange_ld=bool(raw.get("auto_arrange_ld", cls.auto_arrange_ld)),
                auto_shutdown_pc=bool(raw.get("auto_shutdown_pc", cls.auto_shutdown_pc)),
                task_type=str(raw.get("task_type", cls.task_type)),
                task_template=str(raw.get("task_template", cls.task_template)),
                scroll_after_post=bool(raw.get("scroll_after_post", cls.scroll_after_post)),
                clear_cache=bool(raw.get("clear_cache", cls.clear_cache)),
                verify_account=bool(raw.get("verify_account", cls.verify_account)),
                reg_contact_mode=str(raw.get("reg_contact_mode", cls.reg_contact_mode)),
                reg_contact_value=str(raw.get("reg_contact_value", cls.reg_contact_value)),
                reg_phone_prefix=str(raw.get("reg_phone_prefix", cls.reg_phone_prefix)),
                email_provider=provider,
                email_address=str(raw.get("email_address", cls.email_address)),
                email_app_password=str(raw.get("email_app_password", cls.email_app_password)),
                email_imap_server=str(raw.get("email_imap_server", provider_defaults.imap_server)),
                email_imap_port=int(raw.get("email_imap_port", provider_defaults.imap_port)),
                email_mailbox=str(raw.get("email_mailbox", provider_defaults.mailbox)),
                email_use_ssl=bool(raw.get("email_use_ssl", provider_defaults.use_ssl)),
                email_unread_only=bool(raw.get("email_unread_only", request_defaults.unread_only)),
                email_sender_filter=str(raw.get("email_sender_filter", request_defaults.sender_filter)),
                email_subject_filter=str(raw.get("email_subject_filter", request_defaults.subject_filter)),
                email_timeout_seconds=int(raw.get("email_timeout_seconds", request_defaults.timeout_seconds)),
                email_poll_interval_seconds=int(raw.get("email_poll_interval_seconds", request_defaults.poll_interval_seconds)),
                email_mark_as_seen=bool(raw.get("email_mark_as_seen", request_defaults.mark_as_seen)),
                ld_groups=ld_groups,
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
