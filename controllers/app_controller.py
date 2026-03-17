from __future__ import annotations

from typing import Callable

from core.settings import (
    AppSettings,
    ScheduleSettings,
    SettingsError,
)
from services.settings_service import SettingsService


class AppController:
    """Coordinates non-UI application concerns for the main window."""

    def __init__(
        self,
        settings_service: SettingsService,
        log_func: Callable[[str, str], None] | None = None,
    ) -> None:
        self.settings_service = settings_service
        self._log = log_func

    def load_app_settings(self) -> AppSettings:
        try:
            return self.settings_service.load_app_settings()
        except SettingsError as exc:
            self._safe_log(f"Failed to load settings: {exc}", "WARNING")
            return AppSettings()

    def save_app_settings(self, settings: AppSettings) -> bool:
        try:
            self.settings_service.save_app_settings(settings)
            return True
        except SettingsError as exc:
            self._safe_log(f"Failed to save settings: {exc}", "WARNING")
            return False

    def load_schedule_settings(self) -> ScheduleSettings:
        try:
            return self.settings_service.load_schedule_settings()
        except SettingsError as exc:
            self._safe_log(f"Failed to load schedule settings: {exc}", "WARNING")
            return ScheduleSettings()

    def save_schedule_settings(self, settings: ScheduleSettings) -> bool:
        try:
            self.settings_service.save_schedule_settings(settings)
            return True
        except SettingsError as exc:
            self._safe_log(f"Failed to save schedule settings: {exc}", "WARNING")
            return False

    def _safe_log(self, message: str, level: str) -> None:
        if callable(self._log):
            self._log(message, level)
