from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.paths import AppPaths
from core.tasks.handler.handler_reg import RegAccountHandlerMixin


def build_test_paths(root: Path) -> AppPaths:
    config_dir = root / "config"
    return AppPaths(
        project_root=root,
        config_dir=config_dir,
        content_dir=root / "content",
        backup_dir=root / "backups",
        logs_dir=root / "logs",
        settings_file=config_dir / "setting.json",
        schedule_settings_file=config_dir / "setting_schedule.json",
        accounts_file=config_dir / "created_accounts.json",
        content_queue_file=config_dir / "content_queue.json",
        scheduled_tasks_file=config_dir / "scheduled_tasks.json",
    )


class DummyRegHandler(RegAccountHandlerMixin):
    FIRST_NAMES = ["Ada"]
    LAST_NAMES = ["Lovelace"]

    def __init__(self) -> None:
        self.messages: list[str] = []

    def log(self, message: str) -> None:
        self.messages.append(message)


class TestHandlerRegImports(unittest.TestCase):
    def test_build_profile_resolves_account_profile(self) -> None:
        handler = DummyRegHandler()

        profile = handler._build_profile(
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "birth_day": 10,
                "birth_month": 12,
                "birth_year": 2005,
                "gender": "Female",
                "contact_mode": "fixed_email",
                "contact_value": "ada@example.com",
                "password": "Secret123Aa!",
            }
        )

        self.assertEqual(profile.__class__.__name__, "AccountProfile")
        self.assertEqual(profile.first_name, "Ada")
        self.assertEqual(profile.contact_label, "email")
        self.assertEqual(profile.contact_value, "ada@example.com")

    def test_save_created_account_resolves_atomic_write_json(self) -> None:
        handler = DummyRegHandler()
        profile = SimpleNamespace(
            first_name="Ada",
            last_name="Lovelace",
            gender="Female",
            contact_label="email",
            contact_value="ada@example.com",
            password="Secret123Aa!",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = build_test_paths(Path(temp_dir))
            account_file = paths.config_dir / "created_accounts.json"

            with (
                patch("core.tasks.handler.handler_reg.get_app_paths", return_value=paths),
                patch("core.tasks.handler.handler_reg._atomic_write_json") as atomic_write_json,
            ):
                handler._save_created_account(
                    "LDPlayer-1",
                    "127.0.0.1:5555",
                    profile,
                    facebook_uid="12345",
                    account_status="Active",
                )

        atomic_write_json.assert_called_once()
        written_path, written_records = atomic_write_json.call_args.args
        self.assertEqual(written_path, account_file)
        self.assertEqual(len(written_records), 1)
        self.assertEqual(written_records[0]["facebook_uid"], "12345")
        self.assertEqual(written_records[0]["email"], "ada@example.com")
        self.assertEqual(written_records[0]["status"], "Active")


if __name__ == "__main__":
    unittest.main()
