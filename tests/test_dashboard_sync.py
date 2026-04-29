import json
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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
        dashboard._db_login_checked_account_ids = set()
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
                dashboard._dashboard_load_data()
                changed = dashboard._db_sync_snapshot_changes(
                    {"LD A": "emulator-5554"},
                    {"LD Renamed": "emulator-5554"},
                )
                saved = json.loads(dashboard_path.read_text(encoding="utf-8"))

        self.assertTrue(changed)
        self.assertEqual([inst["name"] for inst in saved["instances"]], ["LD Renamed"])
        self.assertEqual(saved["instances"][0]["account"]["pages"], [{"name": "Page A"}])
        self.assertEqual(dashboard._dashboard_selected, "LD Renamed")

    def test_deleted_ld_removes_dashboard_row(self):
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
                            },
                            {
                                "name": "LD B",
                                "account": {
                                    "name": "Facebook B",
                                    "uid": None,
                                    "password": None,
                                    "twofa": None,
                                    "mail": None,
                                    "pages": [{"name": "Page B"}],
                                },
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            dashboard = self._dashboard()
            dashboard._dashboard_selected = "LD A"
            dashboard._dashboard_checked = {"LD A", "LD B"}

            with patch("gui.pages.dashboard_page.get_app_paths", return_value=paths):
                dashboard._dashboard_load_data()
                changed = dashboard._db_sync_snapshot_changes(
                    {"LD A": "emulator-5554", "LD B": "emulator-5556"},
                    {"LD B": "emulator-5556"},
                )
                saved = json.loads(dashboard_path.read_text(encoding="utf-8"))

        self.assertTrue(changed)
        self.assertEqual([inst["name"] for inst in saved["instances"]], ["LD B"])
        self.assertIsNone(dashboard._dashboard_selected)
        self.assertEqual(dashboard._dashboard_checked, {"LD B"})

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

    def test_dashboard_lists_saved_json_instances_without_live_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            (paths.config_dir / "dashboard_instances.json").write_text(
                json.dumps(
                    {
                        "instances": [
                            {"name": "LD Saved A", "serial": "emulator-5554", "account": {"name": "Facebook A"}},
                            {"name": "LD Saved B", "account": {"mail": "b@example.com"}},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            dashboard = self._dashboard()
            dashboard._ld_snapshot = {}

            with patch("gui.pages.dashboard_page.get_app_paths", return_value=paths):
                dashboard._dashboard_load_data()

        self.assertEqual(dashboard._db_device_names(), ["LD Saved A", "LD Saved B"])
        self.assertEqual(dashboard._dashboard_data["instances"][0]["serial"], "emulator-5554")
        self.assertEqual(dashboard._dashboard_data["instances"][1]["account"]["mail"], "b@example.com")

    def test_emulator_table_uses_dashboard_json_instead_of_dev_fallback_instances(self):
        class FakeEmulator:
            def __init__(self):
                self.name_to_serial = {
                    "US - clone": "127.0.0.1:5555",
                    "US - 01": "127.0.0.1:5557",
                    "US - 02": "127.0.0.1:5559",
                    "US - 03": "127.0.0.1:5561",
                    "US - 04": "127.0.0.1:5563",
                    "US - 05": "127.0.0.1:5565",
                }

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            (paths.config_dir / "dashboard_instances.json").write_text(
                json.dumps(
                    {
                        "instances": [
                            {"name": "LD Saved A", "serial": "emulator-5554"},
                            {"name": "LD Saved B"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            app = LDManagerApp.__new__(LDManagerApp)
            app.paths = paths
            app.emulator = FakeEmulator()

            snapshot = app._snapshot_with_dashboard_fallback(dict(app.emulator.name_to_serial))

        self.assertEqual(snapshot, {"LD Saved A": "emulator-5554", "LD Saved B": ""})
        self.assertEqual(app.emulator.name_to_serial, snapshot)

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

    def test_dashboard_checkbox_selection_tracks_visible_rows(self):
        class FakeTree:
            def __init__(self):
                self.text = {"LD A": "", "LD B": ""}

            def get_children(self):
                return tuple(self.text)

            def exists(self, item):
                return item in self.text

            def item(self, item, **kwargs):
                if "text" in kwargs:
                    self.text[item] = kwargs["text"]
                return {"text": self.text[item]}

        dashboard = self._dashboard()
        dashboard._ld_snapshot = {"LD A": "emulator-5554", "LD B": "emulator-5556", "LD C": "emulator-5558"}
        dashboard._db_tree = FakeTree()
        dashboard._db_widget_exists = lambda widget: widget is not None
        dashboard._db_update_checked_count = lambda: None

        dashboard._db_set_checked_instances({"LD A", "LD C"})
        dashboard._db_select_all_visible_instances()

        self.assertEqual(dashboard._dashboard_checked, {"LD A", "LD B", "LD C"})
        self.assertEqual(dashboard._db_tree.text["LD A"], "☑")
        self.assertEqual(dashboard._db_tree.text["LD B"], "☑")

    def test_dashboard_clear_checked_account_data_resets_only_checked_instances(self):
        dashboard = self._dashboard()
        dashboard._ld_snapshot = {"LD A": "emulator-5554", "LD B": "emulator-5556"}
        dashboard._dashboard_checked = {"LD A"}
        dashboard._dashboard_data = {
            "instances": [
                {
                    "name": "LD A",
                    "account": {
                        "name": "Facebook A",
                        "uid": "1001",
                        "password": "pw",
                        "twofa": "secret",
                        "mail": "a@example.com",
                        "pages": [{"name": "Page A"}],
                    },
                },
                {
                    "name": "LD B",
                    "account": {"name": "Facebook B", "uid": None, "mail": None, "pages": [{"name": "Page B"}]},
                },
            ]
        }
        dashboard._db_save_all = lambda: None
        dashboard._db_render_all = lambda: None
        dashboard._db_status = lambda *_args, **_kwargs: None

        with patch("gui.pages.dashboard_page.MessageBox.askyesno", return_value=True):
            dashboard._db_clear_checked_account_data()

        self.assertIsNone(dashboard._dashboard_data["instances"][0]["account"]["name"])
        self.assertEqual(dashboard._dashboard_data["instances"][0]["account"]["pages"], [])
        self.assertEqual(dashboard._dashboard_data["instances"][1]["account"]["name"], "Facebook B")

    def test_dashboard_login_account_parser_accepts_uid_password_email_2fa(self):
        dashboard = self._dashboard()

        accounts = dashboard._db_parse_login_account_lines(
            "100000000001,Password123,user@example.com,ABCD EFGH IJKL MNOP\n"
        )

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["uid"], "100000000001")
        self.assertEqual(accounts[0]["password"], "Password123")
        self.assertEqual(accounts[0]["email"], "user@example.com")
        self.assertEqual(accounts[0]["twofa"], "ABCD EFGH IJKL MNOP")

    def test_dashboard_assign_login_account_updates_instance_account_fields(self):
        dashboard = self._dashboard()
        instance = {
            "name": "LD A",
            "account": {
                "name": None,
                "uid": None,
                "password": None,
                "twofa": None,
                "mail": None,
                "pages": [{"name": "Page A"}],
            },
        }

        dashboard._db_assign_login_account_to_instance(
            instance,
            {
                "uid": "100000000001",
                "password": "Password123",
                "email": "user@example.com",
                "twofa": "ABCD EFGH IJKL MNOP",
            },
        )

        self.assertEqual(instance["account"]["name"], "user@example.com")
        self.assertEqual(instance["account"]["uid"], "100000000001")
        self.assertEqual(instance["account"]["password"], "Password123")
        self.assertEqual(instance["account"]["mail"], "user@example.com")
        self.assertEqual(instance["account"]["twofa"], "ABCD EFGH IJKL MNOP")
        self.assertEqual(instance["account"]["pages"][0]["name"], "Page A")
        self.assertIn("reels", instance["account"]["pages"][0])

    def test_dashboard_login_accounts_save_to_accounts_login_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            dashboard = self._dashboard()

            with patch("gui.pages.dashboard_page.get_app_paths", return_value=paths):
                dashboard._db_save_login_accounts(
                    [
                        {
                            "uid": "100000000001",
                            "password": "Password123",
                            "email": "user@example.com",
                            "twofa": "ABCD EFGH IJKL MNOP",
                        }
                    ]
                )
                saved = json.loads((paths.config_dir / "accounts_login.json").read_text(encoding="utf-8"))

        self.assertEqual(
            saved,
            [
                {
                    "account_id": "100000000001",
                    "uid": "100000000001",
                    "password": "Password123",
                    "email": "user@example.com",
                    "twofa": "ABCD EFGH IJKL MNOP",
                }
            ],
        )

    def test_dashboard_delete_login_accounts_removes_selected_rows(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            dashboard = self._dashboard()

            with patch("gui.pages.dashboard_page.get_app_paths", return_value=paths):
                dashboard._db_save_login_accounts(
                    [
                        {"uid": "1001", "password": "pw-a", "email": "a@example.com", "twofa": ""},
                        {"uid": "1002", "password": "pw-b", "email": "b@example.com", "twofa": ""},
                        {"uid": "1003", "password": "pw-c", "email": "c@example.com", "twofa": ""},
                    ]
                )
                removed = dashboard._db_delete_login_accounts(["1001", "1003"])
                saved = json.loads((paths.config_dir / "accounts_login.json").read_text(encoding="utf-8"))

        self.assertEqual(removed, 2)
        self.assertEqual([account["uid"] for account in saved], ["1002"])

    def test_dashboard_login_account_checkbox_supports_multi_select_and_first_checked(self):
        class FakeTree:
            def __init__(self):
                self.text = {"acct-a": "", "acct-b": "", "acct-c": ""}
                self.selected = None
                self.focused = None

            def get_children(self):
                return tuple(self.text)

            def exists(self, item):
                return item in self.text

            def item(self, item, **kwargs):
                if "text" in kwargs:
                    self.text[item] = kwargs["text"]
                return {"text": self.text[item]}

            def selection_set(self, item):
                self.selected = item

            def focus(self, item):
                self.focused = item

        dashboard = self._dashboard()
        tree = FakeTree()

        dashboard._db_toggle_login_account_checked(tree, "acct-a")
        self.assertEqual(dashboard._db_login_checked_account_id, "acct-a")
        self.assertEqual(tree.text, {"acct-a": "☑", "acct-b": "☐", "acct-c": "☐"})

        dashboard._db_toggle_login_account_checked(tree, "acct-b")
        self.assertEqual(dashboard._db_login_checked_account_id, "acct-a")
        self.assertEqual(dashboard._db_checked_login_account_ids(tree), ["acct-a", "acct-b"])
        self.assertEqual(tree.text, {"acct-a": "☑", "acct-b": "☑", "acct-c": "☐"})

        dashboard._db_toggle_login_account_checked(tree, "acct-a")
        self.assertEqual(dashboard._db_login_checked_account_id, "acct-b")
        self.assertEqual(tree.text, {"acct-a": "☐", "acct-b": "☑", "acct-c": "☐"})

    def test_dashboard_use_login_account_starts_login_task_with_selected_credentials(self):
        class FakeThread:
            def __init__(self, target, daemon=False):
                self.target = target
                self.daemon = daemon

            def start(self):
                self.target()

        class FakeAutomationController:
            def __init__(self, event):
                self.event = event

            def start(self):
                self.event.set()

        dashboard = self._dashboard()
        dashboard.emulator = Mock()
        dashboard.pause_event = Mock()
        dashboard.running_event = threading.Event()
        dashboard.automation_controller = FakeAutomationController(dashboard.running_event)
        dashboard.update_device_runtime_state = Mock()
        dashboard.stop_automation = Mock(side_effect=lambda confirm=False: dashboard.running_event.clear())
        dashboard.log = Mock()

        handler = Mock()
        handler.execute.return_value = True

        with patch("gui.pages.dashboard_page.threading.Thread", FakeThread), patch(
            "core.logic.login_account.LoginAccountTaskHandler",
            return_value=handler,
        ):
            dashboard._db_start_login_account_task(
                {"name": "LD A"},
                {
                    "uid": "100000000001",
                    "password": "Password123",
                    "email": "user@example.com",
                    "twofa": "ABCD EFGH IJKL MNOP",
                },
            )

        handler.execute.assert_called_once()
        args, kwargs = handler.execute.call_args
        self.assertEqual(args[0], "LD A")
        self.assertEqual(kwargs["identifier"], "100000000001")
        self.assertEqual(kwargs["identifier_label"], "uid")
        self.assertEqual(kwargs["email"], "user@example.com")
        self.assertEqual(kwargs["password"], "Password123")
        self.assertEqual(kwargs["twofa"], "ABCD EFGH IJKL MNOP")
        self.assertEqual(kwargs["twofa_secret"], "ABCD EFGH IJKL MNOP")
        self.assertTrue(kwargs["verify_2fa"])
        dashboard.stop_automation.assert_called_once_with(confirm=False)

    def test_dashboard_login_task_uses_email_when_uid_is_missing(self):
        class FakeThread:
            def __init__(self, target, daemon=False):
                self.target = target

            def start(self):
                self.target()

        class FakeAutomationController:
            def __init__(self, event):
                self.event = event

            def start(self):
                self.event.set()

        dashboard = self._dashboard()
        dashboard.emulator = Mock()
        dashboard.pause_event = Mock()
        dashboard.running_event = threading.Event()
        dashboard.automation_controller = FakeAutomationController(dashboard.running_event)
        dashboard.update_device_runtime_state = Mock()
        dashboard.stop_automation = Mock(side_effect=lambda confirm=False: dashboard.running_event.clear())
        dashboard.log = Mock()

        handler = Mock()
        handler.execute.return_value = True

        with patch("gui.pages.dashboard_page.threading.Thread", FakeThread), patch(
            "core.logic.login_account.LoginAccountTaskHandler",
            return_value=handler,
        ):
            dashboard._db_start_login_account_task(
                {"name": "LD A"},
                {
                    "uid": "",
                    "password": "Password123",
                    "email": "user@example.com",
                    "twofa": "",
                },
            )

        _, kwargs = handler.execute.call_args
        self.assertEqual(kwargs["identifier"], "user@example.com")
        self.assertEqual(kwargs["identifier_label"], "email")


if __name__ == "__main__":
    unittest.main()
