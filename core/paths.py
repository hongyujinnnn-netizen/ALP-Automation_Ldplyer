from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    project_root: Path
    config_dir: Path
    content_dir: Path
    backup_dir: Path
    logs_dir: Path
    settings_file: Path
    schedule_settings_file: Path
    accounts_file: Path
    content_queue_file: Path
    scheduled_tasks_file: Path

    def ensure_runtime_dirs(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.content_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


def get_app_paths() -> AppPaths:
    project_root = Path(__file__).resolve().parents[1]
    config_dir = project_root / "config"

    return AppPaths(
        project_root=project_root,
        config_dir=config_dir,
        content_dir=project_root / "content",
        backup_dir=project_root / "backups",
        logs_dir=project_root / "logs",
        settings_file=config_dir / "setting.json",
        schedule_settings_file=config_dir / "setting_schedule.json",
        accounts_file=config_dir / "accounts.json",
        content_queue_file=config_dir / "content_queue.json",
        scheduled_tasks_file=config_dir / "scheduled_tasks.json",
    )
