import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.paths import AppPaths
from core.tasks.task_reels import ReelsTaskHandler


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


class TestReelsExecutePageLoop(unittest.TestCase):
    def test_back_to_account_profile_uses_dashboard_switch_profile_content_desc(self):
        logs = []
        emulator = Mock()
        pause_event = Mock()
        handler = ReelsTaskHandler(
            emulator,
            lambda message, level="INFO": logs.append(message),
            pause_event,
            lambda: True,
        )

        clicked = Mock()
        clicked.exists = True
        device = Mock()
        device.xpath.return_value = clicked

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            (paths.config_dir / "dashboard_instances.json").write_text(
                json.dumps(
                    {
                        "instances": [
                            {
                                "name": "US - 01",
                                "account": {"name": "Osaka Chuii"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch("core.tasks.task_reels.get_app_paths", return_value=paths):
                result = handler.back_to_account_profile(device, "US - 01")

        self.assertTrue(result)
        device.xpath.assert_called_with(
            '//android.widget.Button[@content-desc="Osaka Chuii, switch into your profile"]'
        )
        clicked.click.assert_called_once()

    def test_detected_pages_update_dashboard_account_and_pages(self):
        logs = []
        emulator = Mock()
        pause_event = Mock()
        handler = ReelsTaskHandler(
            emulator,
            lambda message, level="INFO": logs.append(message),
            pause_event,
            lambda: True,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            dashboard_path = paths.config_dir / "dashboard_instances.json"
            dashboard_path.write_text(
                json.dumps(
                    {
                        "instances": [
                            {
                                "name": "Ryu S. Kennedy",
                                "account": {
                                    "uid": None,
                                    "password": None,
                                    "twofa": None,
                                    "mail": None,
                                    "pages": [
                                        {
                                            "name": "Jamreel",
                                            "page_id": "123",
                                            "reels": {"enabled": True},
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch("core.tasks.task_reels.get_app_paths", return_value=paths):
                synced = handler._sync_detected_pages_to_dashboard(
                    "Ryu S. Kennedy",
                    ["Leon S. Kennedy", "Jamreel", "Demoworld", "meiileungg"],
                )

            saved = json.loads(dashboard_path.read_text(encoding="utf-8"))

        self.assertTrue(synced)
        account = saved["instances"][0]["account"]
        self.assertEqual(account["name"], "Leon S. Kennedy")
        self.assertEqual([page["name"] for page in account["pages"]], ["Jamreel", "Demoworld", "meiileungg"])
        self.assertEqual(account["pages"][0]["page_id"], "123")
        self.assertTrue(account["pages"][0]["reels"]["enabled"])
        self.assertTrue(account["pages"][1]["reels"]["enabled"])
        self.assertTrue(account["pages"][2]["reels"]["enabled"])
        self.assertIn("Updated dashboard config for Ryu S. Kennedy", logs[-1])

    def _make_sync_handler(self, logs, shared_dir):
        emulator = Mock()
        emulator.get_shared_folder = Mock(return_value=str(shared_dir))
        pause_event = Mock()
        return ReelsTaskHandler(
            emulator,
            lambda message, level="INFO": logs.append(message),
            pause_event,
            lambda: True,
        )

    def test_auto_assign_source_subfolders_by_index_skips_ld_launcher(self):
        logs = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = build_test_paths(root)
            paths.ensure_runtime_dirs()
            shared = root / "shared"
            shared.mkdir()
            for name in ("Alpha", "Bravo", "Charlie", "ld_launcher"):
                (shared / name).mkdir()

            handler = self._make_sync_handler(logs, shared)

            dashboard_path = paths.config_dir / "dashboard_instances.json"
            dashboard_path.write_text(json.dumps({"instances": []}), encoding="utf-8")

            with patch("core.tasks.task_reels.get_app_paths", return_value=paths):
                handler._sync_detected_pages_to_dashboard(
                    "LD-1",
                    ["MainAccount", "Page1", "Page2", "Page3"],
                )

            saved = json.loads(dashboard_path.read_text(encoding="utf-8"))

        pages = saved["instances"][0]["account"]["pages"]
        self.assertEqual(
            [p["reels"]["source_subfolder"] for p in pages],
            ["Alpha", "Bravo", "Charlie"],
        )
        for p in pages:
            self.assertNotEqual(p["reels"]["source_subfolder"].lower(), "ld_launcher")

    def test_auto_assign_single_folder_shared_by_all_pages(self):
        logs = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = build_test_paths(root)
            paths.ensure_runtime_dirs()
            shared = root / "shared"
            shared.mkdir()
            (shared / "OnlyOne").mkdir()
            (shared / "ld_launcher").mkdir()

            handler = self._make_sync_handler(logs, shared)

            dashboard_path = paths.config_dir / "dashboard_instances.json"
            dashboard_path.write_text(json.dumps({"instances": []}), encoding="utf-8")

            with patch("core.tasks.task_reels.get_app_paths", return_value=paths):
                handler._sync_detected_pages_to_dashboard(
                    "LD-1",
                    ["MainAccount", "Page1", "Page2", "Page3"],
                )

            saved = json.loads(dashboard_path.read_text(encoding="utf-8"))

        pages = saved["instances"][0]["account"]["pages"]
        self.assertEqual(
            [p["reels"]["source_subfolder"] for p in pages],
            ["OnlyOne", "OnlyOne", "OnlyOne"],
        )

    def test_auto_assign_preserves_valid_manual_override(self):
        logs = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = build_test_paths(root)
            paths.ensure_runtime_dirs()
            shared = root / "shared"
            shared.mkdir()
            for name in ("Alpha", "Bravo", "Charlie"):
                (shared / name).mkdir()

            handler = self._make_sync_handler(logs, shared)

            dashboard_path = paths.config_dir / "dashboard_instances.json"
            dashboard_path.write_text(
                json.dumps(
                    {
                        "instances": [
                            {
                                "name": "LD-1",
                                "account": {
                                    "name": "MainAccount",
                                    "pages": [
                                        {
                                            "name": "Page1",
                                            "reels": {"source_subfolder": "Charlie"},
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch("core.tasks.task_reels.get_app_paths", return_value=paths):
                handler._sync_detected_pages_to_dashboard(
                    "LD-1",
                    ["MainAccount", "Page1", "Page2", "Page3"],
                )

            saved = json.loads(dashboard_path.read_text(encoding="utf-8"))

        pages = {p["name"]: p["reels"]["source_subfolder"] for p in saved["instances"][0]["account"]["pages"]}
        self.assertEqual(pages["Page1"], "Charlie")
        self.assertEqual(pages["Page2"], "Bravo")
        self.assertEqual(pages["Page3"], "Charlie")

    def test_execute_uses_dashboard_pages_without_detecting_when_present(self):
        logs = []
        emulator = Mock()
        emulator.is_ld_running.return_value = True
        emulator.name_to_serial = {"US - 01": "127.0.0.1:5555"}

        pause_event = Mock()
        pause_event.is_set.return_value = True

        handler = ReelsTaskHandler(
            emulator,
            lambda message, level="INFO": logs.append(message),
            pause_event,
            lambda: True,
        )
        handler.ensure_device_ready = Mock(return_value=True)
        handler.push_runtime_state = Mock()
        handler.rate_limiter = Mock()
        handler.rate_limiter.can_perform_action.return_value = True

        clicked_pages = []
        clicked_page_indexes = []
        folder_names = []

        handler.open_facebook = Mock(return_value=True)
        handler.click_facebook_menu = Mock(return_value=True)
        handler.click_profile_dropdown = Mock(return_value=True)
        handler.detect_facebook_page = Mock(
            side_effect=AssertionError("dashboard pages should skip detection")
        )
        handler.click_on_page = Mock(
            side_effect=lambda d, pages, page_to_click: (
                clicked_pages.append(list(pages)) or clicked_page_indexes.append(page_to_click) or True
            )
        )
        handler._open_file_manager_with_retry = Mock(return_value=True)
        handler.navigate_to_pictures = Mock(return_value=True)
        handler.click_folder_post_page = Mock(
            side_effect=lambda d, folder_name: folder_names.append(folder_name) or True
        )
        handler.hold_on_video = Mock(return_value=True)
        handler.handle_context_menu_after_long_press = Mock(return_value=True)
        handler.check_and_handle_facebook_permission = Mock(return_value=False)
        handler.facebook_first_next = Mock(return_value=True)
        handler.handle_reels_description = Mock(return_value=True)
        handler.delete_video = Mock(return_value=True)
        handler.end_to_accoutn_profile = Mock(return_value=True)
        handler.scroll_facebook_reels = Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            (paths.config_dir / "dashboard_instances.json").write_text(
                json.dumps(
                    {
                        "instances": [
                            {
                                "name": "US - 01",
                                "account": {
                                    "name": "Facebook A",
                                    "pages": [
                                        {"name": "Page A", "reels": {"source_subfolder": "FolderA"}},
                                        {"name": "Page B", "reels": {"source_subfolder": "FolderB"}},
                                    ],
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("core.tasks.task_reels.U2_AVAILABLE", True),
                patch("core.tasks.task_reels.u2") as mock_u2,
                patch("core.tasks.task_reels.time.sleep", return_value=None),
                patch("core.tasks.task_reels.get_app_paths", return_value=paths),
            ):
                device = Mock()
                device.serial = "127.0.0.1:5555"
                selector = Mock()
                selector.exists.return_value = True
                device.return_value = selector
                mock_u2.connect.return_value = device

                result = handler.execute(
                    "US - 01",
                    max_videos=1,
                    page_per_account=2,
                    scroll_after_post=False,
                    use_content_queue=False,
                )

        self.assertTrue(result)
        self.assertEqual(clicked_pages, [["Page A", "Page B"], ["Page A", "Page B"]])
        self.assertEqual(clicked_page_indexes, [0, 1])
        self.assertEqual(folder_names, ["FolderA", "FolderB"])
        handler.detect_facebook_page.assert_not_called()
        self.assertIn("Using dashboard page names on US - 01: ['Page A', 'Page B']", logs)

    def test_execute_posts_all_videos_for_each_page_before_switching(self):
        logs = []
        emulator = Mock()
        emulator.is_ld_running.return_value = True
        emulator.name_to_serial = {"US - 01": "127.0.0.1:5555"}

        pause_event = Mock()
        pause_event.is_set.return_value = True

        handler = ReelsTaskHandler(
            emulator,
            lambda message, level="INFO": logs.append(message),
            pause_event,
            lambda: True,
        )
        handler.ensure_device_ready = Mock(return_value=True)
        handler.push_runtime_state = Mock()
        handler.rate_limiter = Mock()
        handler.rate_limiter.can_perform_action.return_value = True

        clicked_page_indexes = []
        folder_names = []

        handler.open_facebook = Mock(return_value=True)
        handler.click_facebook_menu = Mock(return_value=True)
        handler.click_profile_dropdown = Mock(return_value=True)
        handler.detect_facebook_page = Mock(return_value=["Facebook A", "Page A", "Page B"])
        handler.click_on_page = Mock(
            side_effect=lambda d, pages, page_to_click: clicked_page_indexes.append(page_to_click) or True
        )
        handler._open_file_manager_with_retry = Mock(return_value=True)
        handler.navigate_to_pictures = Mock(return_value=True)
        handler.click_folder_post_page = Mock(
            side_effect=lambda d, folder_name: folder_names.append(folder_name) or True
        )
        handler.hold_on_video = Mock(return_value=True)
        handler.handle_context_menu_after_long_press = Mock(return_value=True)
        handler.check_and_handle_facebook_permission = Mock(return_value=False)
        handler.facebook_first_next = Mock(return_value=True)
        handler.handle_reels_description = Mock(return_value=True)
        handler.delete_video = Mock(return_value=True)
        handler.end_to_accoutn_profile = Mock(return_value=True)
        handler.scroll_facebook_reels = Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            (paths.config_dir / "dashboard_instances.json").write_text(
                json.dumps(
                    {
                        "instances": [
                            {
                                "name": "US - 01",
                                "account": {
                                    "name": "Facebook A",
                                    "pages": [
                                        {"name": "Page A", "reels": {"source_subfolder": "FolderA"}},
                                        {"name": "Page B", "reels": {"source_subfolder": "FolderB"}},
                                    ],
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("core.tasks.task_reels.U2_AVAILABLE", True),
                patch("core.tasks.task_reels.u2") as mock_u2,
                patch("core.tasks.task_reels.time.sleep", return_value=None),
                patch("core.tasks.task_reels.get_app_paths", return_value=paths),
            ):
                device = Mock()
                device.serial = "127.0.0.1:5555"
                selector = Mock()
                selector.exists.return_value = True
                device.return_value = selector
                mock_u2.connect.return_value = device

                result = handler.execute(
                    "US - 01",
                    max_videos=2,
                    page_per_account=2,
                    scroll_after_post=False,
                    use_content_queue=False,
                )

        self.assertTrue(result)
        self.assertEqual(clicked_page_indexes, [0, 1])
        self.assertEqual(folder_names, ["FolderA", "FolderB"])
        self.assertEqual(handler.hold_on_video.call_count, 4)
        self.assertEqual(handler.delete_video.call_count, 4)
        self.assertEqual(handler.push_runtime_state.call_args_list[-1].kwargs["task"], "Processed 4/4 video")
        self.assertEqual(logs[-1], "Task completed: Processed 4/4 videos successfully")

    def test_execute_reopens_facebook_when_profile_dropdown_fails_once(self):
        logs = []
        emulator = Mock()
        emulator.is_ld_running.return_value = True
        emulator.name_to_serial = {"US - 01": "127.0.0.1:5555"}

        pause_event = Mock()
        pause_event.is_set.return_value = True

        handler = ReelsTaskHandler(
            emulator,
            lambda message, level="INFO": logs.append(message),
            pause_event,
            lambda: True,
        )
        handler.ensure_device_ready = Mock(return_value=True)
        handler.push_runtime_state = Mock()
        handler.rate_limiter = Mock()
        handler.rate_limiter.can_perform_action.return_value = True

        handler.open_facebook = Mock(return_value=True)
        handler.click_facebook_menu = Mock(return_value=True)
        handler.click_profile_dropdown = Mock(side_effect=[False, True])
        handler._clear_recent_apps = Mock()
        handler.detect_facebook_page = Mock(
            side_effect=AssertionError("dashboard pages should skip detection")
        )
        handler.click_on_page = Mock(return_value=True)
        handler._open_file_manager_with_retry = Mock(return_value=True)
        handler.navigate_to_pictures = Mock(return_value=True)
        handler.click_folder_post_page = Mock(return_value=True)
        handler.hold_on_video = Mock(return_value=True)
        handler.handle_context_menu_after_long_press = Mock(return_value=True)
        handler.check_and_handle_facebook_permission = Mock(return_value=False)
        handler.facebook_first_next = Mock(return_value=True)
        handler.handle_reels_description = Mock(return_value=True)
        handler.delete_video = Mock(return_value=True)
        handler.end_to_accoutn_profile = Mock(return_value=True)
        handler.scroll_facebook_reels = Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            (paths.config_dir / "dashboard_instances.json").write_text(
                json.dumps(
                    {
                        "instances": [
                            {
                                "name": "US - 01",
                                "account": {
                                    "name": "Facebook A",
                                    "pages": [
                                        {"name": "Page A", "reels": {"source_subfolder": "FolderA"}},
                                    ],
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("core.tasks.task_reels.U2_AVAILABLE", True),
                patch("core.tasks.task_reels.u2") as mock_u2,
                patch("core.tasks.task_reels.time.sleep", return_value=None),
                patch("core.tasks.task_reels.get_app_paths", return_value=paths),
            ):
                device = Mock()
                device.serial = "127.0.0.1:5555"
                selector = Mock()
                selector.exists.return_value = True
                device.return_value = selector
                mock_u2.connect.return_value = device

                result = handler.execute(
                    "US - 01",
                    max_videos=1,
                    page_per_account=1,
                    scroll_after_post=False,
                    use_content_queue=False,
                )

        self.assertTrue(result)
        self.assertEqual(handler.open_facebook.call_count, 2)
        self.assertEqual(handler.click_facebook_menu.call_count, 2)
        self.assertEqual(handler.click_profile_dropdown.call_count, 2)
        handler._clear_recent_apps.assert_called_once()
        handler.click_on_page.assert_called_once()
        self.assertTrue(any("Restarting Facebook before retry 2/2" in log for log in logs))


if __name__ == "__main__":
    unittest.main()
