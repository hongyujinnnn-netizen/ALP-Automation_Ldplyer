import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.paths import AppPaths
from gui.ld_manager_app import LDManagerApp
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

    def test_emulator_account_cache_prefers_dashboard_account_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            (paths.config_dir / "dashboard_instances.json").write_text(
                json.dumps(
                    {
                        "instances": [
                            {
                                "name": "LD A",
                                "account": {
                                    "name": "Facebook A",
                                    "uid": "1001",
                                    "mail": "a@example.com",
                                    "pages": [],
                                },
                            },
                            {
                                "name": "LD B",
                                "account": {
                                    "name": None,
                                    "uid": None,
                                    "mail": None,
                                    "pages": [],
                                },
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            app = LDManagerApp.__new__(LDManagerApp)
            app.paths = paths

            merged = app._apply_dashboard_account_cache(
                {"LD A": "emulator-5554", "LD B": "emulator-5556"},
                {"LD A": "Old Account", "LD B": "Fallback B"},
            )

        self.assertEqual(merged["LD A"], "Facebook A")
        self.assertEqual(merged["LD B"], "Fallback B")

    def test_ld_drag_toggle_selects_each_visited_row_once(self):
        class FakeTable:
            def __init__(self):
                self.checkboxes = {"i1": False, "i2": False, "i3": False}
                self.selected = None

            def get_children(self):
                return ("i1", "i2", "i3")

            def toggle_checkbox(self, item):
                self.checkboxes[item] = not self.checkboxes[item]

            def select_item(self, item):
                self.selected = item

            def item(self, item, option=None):
                if option == "values":
                    return (item, f"serial-{item}")
                return {"values": (item, f"serial-{item}")}

        app = LDManagerApp.__new__(LDManagerApp)
        app.ld_table = FakeTable()
        app._ld_drag_toggle_visited = set()

        self.assertTrue(app._toggle_ld_row_selection("i1", True))
        self.assertFalse(app._toggle_ld_row_selection("i1", True))
        self.assertTrue(app._toggle_ld_row_selection("i2", True))

        self.assertTrue(app.ld_table.checkboxes["i1"])
        self.assertTrue(app.ld_table.checkboxes["i2"])
        self.assertFalse(app.ld_table.checkboxes["i3"])

    def test_ld_drag_toggle_can_deselect_rows(self):
        class FakeTable:
            def __init__(self):
                self.checkboxes = {"i1": True, "i2": True, "i3": True}

            def toggle_checkbox(self, item):
                self.checkboxes[item] = not self.checkboxes[item]

        app = LDManagerApp.__new__(LDManagerApp)
        app.ld_table = FakeTable()
        app._ld_drag_toggle_visited = set()

        app._toggle_ld_row_selection("i3", False)
        app._toggle_ld_row_selection("i2", False)
        app._toggle_ld_row_selection("i2", False)

        self.assertTrue(app.ld_table.checkboxes["i1"])
        self.assertFalse(app.ld_table.checkboxes["i2"])
        self.assertFalse(app.ld_table.checkboxes["i3"])

    def test_ld_empty_click_clears_selection(self):
        class FakeTable:
            def __init__(self):
                self.checkboxes = {"i1": True, "i2": False, "i3": True}
                self.selected = "i1"

            def get_children(self):
                return ("i1", "i2", "i3")

            def toggle_checkbox(self, item):
                self.checkboxes[item] = not self.checkboxes[item]

            def select_item(self, item):
                self.selected = item

        app = LDManagerApp.__new__(LDManagerApp)
        app.ld_table = FakeTable()
        app.log = lambda *_args, **_kwargs: None

        app._clear_ld_table_selection()

        self.assertEqual(app.ld_table.checkboxes, {"i1": False, "i2": False, "i3": False})
        self.assertIsNone(app.ld_table.selected)

    def test_ld_right_click_unselected_row_selects_only_that_row(self):
        class FakeTable:
            def __init__(self):
                self.checkboxes = {"i1": True, "i2": False, "i3": True}

            def get_children(self):
                return ("i1", "i2", "i3")

            def toggle_checkbox(self, item):
                self.checkboxes[item] = not self.checkboxes[item]

        app = LDManagerApp.__new__(LDManagerApp)
        app.ld_table = FakeTable()
        app.update_selection_info = lambda: None

        app._prepare_ld_context_selection("i2")

        self.assertEqual(app.ld_table.checkboxes, {"i1": False, "i2": True, "i3": False})

    def test_ld_right_click_selected_row_keeps_multi_selection(self):
        class FakeTable:
            def __init__(self):
                self.checkboxes = {"i1": True, "i2": False, "i3": True}

            def get_children(self):
                return ("i1", "i2", "i3")

            def toggle_checkbox(self, item):
                self.checkboxes[item] = not self.checkboxes[item]

        app = LDManagerApp.__new__(LDManagerApp)
        app.ld_table = FakeTable()

        app._prepare_ld_context_selection("i3")

        self.assertEqual(app.ld_table.checkboxes, {"i1": True, "i2": False, "i3": True})


if __name__ == "__main__":
    unittest.main()
