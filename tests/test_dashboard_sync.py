import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.paths import AppPaths
from gui.pages.dashboard_page import DashboardDialogMixin


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


class TestDashboardLdSync(unittest.TestCase):
    def _dashboard(self):
        dashboard = DashboardDialogMixin.__new__(DashboardDialogMixin)
        dashboard._dashboard_data = {"instances": []}
        dashboard._dashboard_dirty = False
        dashboard._dashboard_selected = None
        dashboard._db_status_label = None
        dashboard.palette = {"success": "#00ff00", "warning": "#ffaa00"}
        return dashboard

    def test_new_ld_instance_is_saved_to_dashboard_without_manual_save(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            dashboard = self._dashboard()
            dashboard._ld_snapshot = {"LD A": "emulator-5554"}

            with patch("gui.pages.dashboard_page.get_app_paths", return_value=paths):
                dashboard._db_sync_from_devices()
                saved = json.loads((paths.config_dir / "dashboard_instances.json").read_text(encoding="utf-8"))

        self.assertEqual([inst["name"] for inst in saved["instances"]], ["LD A"])
        self.assertIn("account", saved["instances"][0])

    def test_renamed_ld_updates_existing_dashboard_row_by_serial(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            dashboard_path = paths.config_dir / "dashboard_instances.json"
            dashboard_path.write_text(
                json.dumps(
                    {
                        "instances": [
                            {
                                "name": "LD A",
                                "account": {
                                    "name": "Facebook A",
                                    "uid": None,
                                    "password": None,
                                    "twofa": None,
                                    "mail": None,
                                    "pages": [{"name": "Page A"}],
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            dashboard = self._dashboard()
            dashboard._dashboard_selected = "LD A"

            with patch("gui.pages.dashboard_page.get_app_paths", return_value=paths):
                changed = dashboard._db_sync_snapshot_changes(
                    {"LD A": "emulator-5554"},
                    {"LD Renamed": "emulator-5554"},
                )
                saved = json.loads(dashboard_path.read_text(encoding="utf-8"))

        self.assertTrue(changed)
        self.assertEqual([inst["name"] for inst in saved["instances"]], ["LD Renamed"])
        self.assertEqual(saved["instances"][0]["account"]["pages"], [{"name": "Page A"}])
        self.assertEqual(dashboard._dashboard_selected, "LD Renamed")


if __name__ == "__main__":
    unittest.main()
