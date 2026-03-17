from __future__ import annotations

from core.paths import AppPaths
from core.settings import (
    AppSettings,
    ScheduleSettings,
    load_app_settings,
    load_schedule_settings,
    save_app_settings,
    save_schedule_settings,
)


class SettingsService:
    """Thin service around persisted application settings."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def load_app_settings(self) -> AppSettings:
        return load_app_settings(self.paths.settings_file)

    def save_app_settings(self, settings: AppSettings) -> None:
        save_app_settings(self.paths.settings_file, settings)

    def load_schedule_settings(self) -> ScheduleSettings:
        return load_schedule_settings(self.paths.schedule_settings_file)

    def save_schedule_settings(self, settings: ScheduleSettings) -> None:
        save_schedule_settings(self.paths.schedule_settings_file, settings)
